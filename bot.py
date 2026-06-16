import os
import random
import time
import threading
import json
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request
from config import BOT_TOKEN, BOT_OWNER_ID, TIMER_SECONDS, MODES, STARTING_COINS, MIN_BET, MAX_BET

# ===== INITIALIZATION =====
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ===== GAME STORAGE =====
active_games = {}
game_timers = {}
game_history = {}

# ===== HELPER FUNCTIONS =====

def is_admin_or_creator(message, game):
    """Check if user is group admin OR game creator"""
    # Check if bot owner
    if message.from_user.id == BOT_OWNER_ID:
        return True
    
    # Check if game creator
    if game and game.creator_id == message.from_user.id:
        return True
    
    # Check if group admin
    try:
        chat_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status in ['administrator', 'creator']:
            return True
    except:
        pass
    
    return False

def is_bot_owner(message):
    return message.from_user.id == BOT_OWNER_ID

def get_player_name(user):
    return user.first_name or user.username or "Player"

def save_game_data():
    try:
        data = {"games": {}, "history": game_history}
        for chat_id, game in active_games.items():
            data["games"][str(chat_id)] = {
                "mode": game.mode,
                "players": game.players,
                "roles": game.roles,
                "current_level": game.current_level,
                "status": game.status,
                "card_map": game.card_map,
                "swap_history": game.swap_history,
                "creator_id": game.creator_id
            }
        with open("game_data.json", "w") as f:
            json.dump(data, f)
    except:
        pass

def load_game_data():
    try:
        with open("game_data.json", "r") as f:
            data = json.load(f)
            return data
    except:
        return {"games": {}, "history": {}}

def check_dm_access(player_id):
    """Check if bot can DM the player"""
    try:
        bot.send_chat_action(player_id, 'typing')
        return True
    except:
        return False

def delete_message(chat_id, message_id):
    """Safely delete a message"""
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

# ===== INLINE KEYBOARD FUNCTIONS =====

def get_player_buttons(game, seeker_id, chat_id):
    """Generate inline keyboard with player names for group"""
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for p in game.players:
        if p["id"] != seeker_id:
            buttons.append(InlineKeyboardButton(
                p["name"], 
                callback_data=f"guess_{chat_id}_{p['id']}_{seeker_id}"
            ))
    # Add cancel button
    buttons.append(InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{chat_id}"))
    markup.add(*buttons)
    return markup

def get_mode_buttons():
    """Generate inline keyboard for mode selection"""
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("👑 4 Players", callback_data="mode_4"),
        InlineKeyboardButton("👑 6 Players", callback_data="mode_6"),
        InlineKeyboardButton("👑 8 Players", callback_data="mode_8"),
        InlineKeyboardButton("👑 10 Players", callback_data="mode_10")
    ]
    markup.add(*buttons)
    return markup

# ===== GAME CLASS =====

class Game:
    def __init__(self, mode=4, creator_id=None):
        self.mode = mode
        self.creator_id = creator_id
        self.players = []
        self.roles = MODES[mode]["roles"].copy()
        self.points = MODES[mode]["points"].copy()
        self.targets = MODES[mode]["targets"].copy()
        self.current_level = 0
        self.status = "waiting"
        self.card_map = {}
        self.swap_history = []
        self.start_time = None
        self.total_rounds = 0
        self.bets = {}
        self.start_message_id = None  # Store the start message to delete later
        
    def add_player(self, player_id, player_name):
        if len(self.players) >= self.mode:
            return False, f"❌ Maximum {self.mode} players reached!"
        if player_id in [p["id"] for p in self.players]:
            return False, "❌ You're already in the game!"
        
        if not check_dm_access(player_id):
            return False, f"❌ {player_name}, please start the bot in DM first! Send /start to @{bot.get_me().username}"
        
        self.players.append({
            "id": player_id, 
            "name": player_name, 
            "coins": STARTING_COINS, 
            "points": 0,
            "joined_at": datetime.now().isoformat()
        })
        return True, f"✅ {player_name} joined! ({len(self.players)}/{self.mode})"
    
    def start_game(self):
        if len(self.players) < 4:
            return False, f"❌ Need at least 4 players! ({len(self.players)} currently)"
        if len(self.players) != self.mode:
            return False, f"❌ This mode needs {self.mode} players! {len(self.players)} joined."
        
        for p in self.players:
            if not check_dm_access(p["id"]):
                return False, f"❌ {p['name']} hasn't started the bot in DM! They need to send /start to @{bot.get_me().username} first."
        
        shuffled_roles = self.roles.copy()
        random.shuffle(shuffled_roles)
        for i, player in enumerate(self.players):
            self.card_map[player["id"]] = shuffled_roles[i]
            player["points"] = 0
            player["coins"] = STARTING_COINS
        
        self.status = "playing"
        self.start_time = time.time()
        self.current_level = 0
        self.total_rounds += 1
        self.bets = {}
        
        seeker = self.get_current_seeker()
        target = self.targets[self.current_level]
        
        return True, {
            "message": f"🎮 Game started! {len(self.players)} players, {self.mode}-Player Mode",
            "seeker": seeker,
            "target": target,
            "points": self.points[self.current_level]
        }
    
    def get_current_seeker(self):
        role = self.roles[self.current_level]
        for player in self.players:
            if self.card_map.get(player["id"]) == role:
                return player
        return None
    
    def get_target_role(self):
        return self.targets[self.current_level]
    
    def get_points(self):
        return self.points[self.current_level]
    
    def make_guess(self, seeker_id, chosen_player_id):
        if self.status != "playing":
            return False, "❌ Game is not active!"
        
        seeker = self.get_current_seeker()
        if not seeker or seeker["id"] != seeker_id:
            return False, "❌ It's not your turn!"
        
        target_role = self.targets[self.current_level]
        chosen_role = self.card_map.get(chosen_player_id, "Unknown")
        chosen_player = self.get_player(chosen_player_id)
        
        if not chosen_player:
            return False, "❌ Player not found!"
        
        bet_amount = self.bets.get(seeker_id, 0)
        
        if chosen_role == target_role:
            points = self.points[self.current_level]
            seeker["points"] += points
            
            if bet_amount > 0:
                seeker["coins"] += bet_amount * 2
                bet_msg = f"💰 Won {bet_amount * 2} coins from bet!"
            else:
                bet_msg = ""
            
            self.current_level += 1
            
            if self.current_level >= len(self.targets):
                self.status = "ended"
                return True, {
                    "result": "correct",
                    "message": f"🎉🏆 {seeker['name']} found {target_role}! GAME OVER! Winner: {seeker['name']} with {seeker['points']} points! {bet_msg}",
                    "points": points,
                    "game_over": True
                }
            else:
                next_seeker = self.get_current_seeker()
                return True, {
                    "result": "correct",
                    "message": f"✅ {seeker['name']} found {target_role}! +{points} points! 🎉 {bet_msg}",
                    "points": points,
                    "next_seeker": next_seeker["name"] if next_seeker else "Unknown",
                    "next_target": self.targets[self.current_level],
                    "next_points": self.points[self.current_level]
                }
        else:
            old_seeker_role = self.card_map[seeker_id]
            old_chosen_role = self.card_map[chosen_player_id]
            
            self.card_map[seeker_id] = old_chosen_role
            self.card_map[chosen_player_id] = old_seeker_role
            
            if bet_amount > 0:
                seeker["coins"] -= bet_amount
                bet_msg = f"💰 Lost {bet_amount} coins from bet!"
            else:
                bet_msg = ""
            
            self.swap_history.append({
                "time": time.time(),
                "seeker": seeker["name"],
                "chosen": chosen_player["name"],
                "swapped": f"{old_seeker_role} ↔ {old_chosen_role}"
            })
            
            new_seeker = self.get_current_seeker()
            return True, {
                "result": "wrong",
                "message": f"❌ WRONG! {seeker['name']} pointed at {chosen_player['name']} (had {chosen_role}) {bet_msg}",
                "swap": f"🔄 Swapped: {old_seeker_role} ↔ {old_chosen_role}",
                "new_seeker": new_seeker["name"] if new_seeker else "Unknown"
            }
    
    def get_player(self, player_id):
        for p in self.players:
            if p["id"] == player_id:
                return p
        return None
    
    def get_player_role(self, player_id):
        return self.card_map.get(player_id, "Unknown")
    
    def get_status(self):
        if self.status == "waiting":
            return f"⏳ Waiting for players... ({len(self.players)}/{self.mode})"
        elif self.status == "playing":
            seeker = self.get_current_seeker()
            target = self.targets[self.current_level]
            points = self.points[self.current_level]
            return f"🎯 Level {self.current_level+1}/{len(self.targets)}: {seeker['name']} searching for {target} (+{points} points)"
        else:
            return "🏁 Game Over!"
    
    def get_leaderboard(self):
        return sorted(self.players, key=lambda x: x["points"], reverse=True)
    
    def get_coin_leaderboard(self):
        return sorted(self.players, key=lambda x: x["coins"], reverse=True)

# ===== TIMER SYSTEM =====

def start_timer(chat_id, game):
    def timer_func():
        time.sleep(TIMER_SECONDS)
        if chat_id in active_games and active_games[chat_id].status == "playing":
            current_game = active_games[chat_id]
            seeker = current_game.get_current_seeker()
            
            if seeker:
                try:
                    bot.send_message(chat_id, f"⏱️ **TIME'S UP!** {seeker['name']} took too long!\n❌ Counted as WRONG guess!", parse_mode='Markdown')
                    
                    others = [p for p in current_game.players if p["id"] != seeker["id"]]
                    if others:
                        random_target = random.choice(others)
                        success, result = current_game.make_guess(seeker["id"], random_target["id"])
                        
                        if success:
                            if result["result"] == "correct":
                                if result.get("game_over"):
                                    bot.send_message(chat_id, f"🎉🏆 {result['message']}")
                                    show_leaderboard_func(chat_id)
                                else:
                                    bot.send_message(chat_id, 
                                        f"{result['message']}\n\n"
                                        f"👑 Next Seeker: {result['next_seeker']}\n"
                                        f"🎯 Target: {result['next_target']}\n"
                                        f"⭐ Points: {result['next_points']}"
                                    )
                                    start_timer(chat_id, current_game)
                            else:
                                bot.send_message(chat_id, 
                                    f"{result['message']}\n{result['swap']}\n\n"
                                    f"👑 New Seeker: {result['new_seeker']}"
                                )
                                start_timer(chat_id, current_game)
                except Exception as e:
                    print(f"Timer error: {e}")
    
    timer_thread = threading.Thread(target=timer_func, daemon=True)
    game_timers[chat_id] = timer_thread
    timer_thread.start()

def reset_timer(chat_id, game):
    start_timer(chat_id, game)

def show_leaderboard_func(chat_id):
    if chat_id not in active_games:
        return
    game = active_games[chat_id]
    sorted_players = game.get_leaderboard()
    msg = "🏆 **POINTS LEADERBOARD** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(sorted_players):
        medal = medals[i] if i < 3 else f"{i+1}."
        role = game.get_player_role(p["id"])
        msg += f"{medal} {p['name']} - **{p['points']}** pts ({role})\n"
    bot.send_message(chat_id, msg, parse_mode='Markdown')

# ===== CALLBACK HANDLERS =====

@bot.callback_query_handler(func=lambda call: call.data.startswith('guess_'))
def handle_guess(call):
    try:
        _, chat_id_str, chosen_id_str, seeker_id_str = call.data.split('_')
        chat_id = int(chat_id_str)
        chosen_id = int(chosen_id_str)
        seeker_id = int(seeker_id_str)
        
        user_id = call.from_user.id
        
        if user_id != seeker_id:
            bot.answer_callback_query(call.id, "❌ It's not your turn!", show_alert=True)
            return
        
        if chat_id not in active_games:
            bot.answer_callback_query(call.id, "❌ No active game!", show_alert=True)
            return
        
        game = active_games[chat_id]
        
        success, result = game.make_guess(seeker_id, chosen_id)
        
        if success:
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except:
                pass
            
            if result["result"] == "correct":
                if result.get("game_over"):
                    bot.send_message(chat_id, f"🎉🏆 **{result['message']}**", parse_mode='Markdown')
                    show_leaderboard_func(chat_id)
                    save_game_data()
                else:
                    next_seeker = game.get_current_seeker()
                    bot.send_message(
                        chat_id,
                        f"{result['message']}\n\n"
                        f"👑 **Next Seeker:** {next_seeker['name']}\n"
                        f"🎯 **Target:** {result['next_target']}\n"
                        f"⭐ **Points:** {result['next_points']}\n\n"
                        f"💡 Click a button to guess!",
                        reply_markup=get_player_buttons(game, next_seeker["id"], chat_id)
                    )
                    reset_timer(chat_id, game)
                    save_game_data()
            else:
                new_seeker = game.get_current_seeker()
                bot.send_message(
                    chat_id,
                    f"{result['message']}\n{result['swap']}\n\n"
                    f"👑 **New Seeker:** {new_seeker['name']}\n"
                    f"⏱️ Timer restarted!\n\n"
                    f"💡 Click a button to guess!",
                    reply_markup=get_player_buttons(game, new_seeker["id"], chat_id)
                )
                reset_timer(chat_id, game)
                save_game_data()
        else:
            bot.answer_callback_query(call.id, f"❌ {result}", show_alert=True)
            
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mode_'))
def handle_mode(call):
    try:
        mode = int(call.data.split('_')[1])
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        if chat_id in active_games and active_games[chat_id].status == "playing":
            bot.answer_callback_query(call.id, "❌ Can't change mode during game!", show_alert=True)
            return
        
        active_games[chat_id] = Game(mode=mode, creator_id=user_id)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        bot.send_message(
            chat_id,
            f"✅ Mode set to {mode}-Player mode!\n"
            f"👑 Game Creator: {call.from_user.first_name}\n\n"
            f"📌 Use /game to join!\n"
            f"🚀 Use /start to begin the game (Creator or Admin only)!",
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, f"✅ {mode}-Player mode set!")
        save_game_data()
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def handle_cancel(call):
    chat_id = int(call.data.split('_')[1])
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    bot.answer_callback_query(call.id, "❌ Cancelled")

# ===== BOT COMMANDS =====

@bot.message_handler(commands=['start'])
def start_command(message):
    chat_id = message.chat.id
    
    # DM - Show help
    if chat_id > 0:
        send_help(message)
        return
    
    # Group - Check if user can start
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No game found! Use /game to create one.")
        return
    
    game = active_games[chat_id]
    
    if game.status != "waiting":
        bot.reply_to(message, "❌ Game already started or ended!")
        return
    
    # Check if user is admin OR creator
    if not is_admin_or_creator(message, game):
        bot.reply_to(message, "❌ Only the game creator or group admin can start the game!")
        return
    
    # Delete the /start command message (so it's not visible)
    try:
        bot.delete_message(chat_id, message.message_id)
    except:
        pass
    
    # Start the game
    success, result = game.start_game()
    
    if success:
        # Send role cards via DM
        for player in game.players:
            role = game.get_player_role(player["id"])
            try:
                bot.send_message(
                    player["id"], 
                    f"🃏 Your role: **{role}**\n🤫 Don't tell anyone!\n💰 Coins: {STARTING_COINS}",
                    parse_mode='Markdown'
                )
            except:
                pass
        
        # Send group message with inline buttons
        msg = bot.send_message(
            chat_id, 
            f"🎮 **GAME STARTED!**\n\n"
            f"👑 **Seeker:** {result['seeker']['name']}\n"
            f"🎯 **Target:** {result['target']}\n"
            f"⭐ **Points:** {result['points']}\n"
            f"⏱️ You have **{TIMER_SECONDS}** seconds!\n\n"
            f"💡 Click a button to guess!",
            reply_markup=get_player_buttons(game, result['seeker']["id"], chat_id),
            parse_mode='Markdown'
        )
        
        # Store message ID so we can delete it later if needed
        game.start_message_id = msg.message_id
        
        start_timer(chat_id, game)
        save_game_data()
    else:
        bot.send_message(chat_id, f"❌ {result}")

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
🎮 **RAJA RANI BOT** 🎮

**👋 Welcome!**

📌 **How to Play:**

**1. Create/Join Game:**
`/game` - Create or join a game in group

**2. Choose Mode:**
Click the mode buttons (4/6/8/10 players)

**3. Start Game (Creator or Admin only):**
`/start` - Start the game in group

**4. During Game:**
Click player buttons to guess!

**💰 Betting:**
`/bet X` - Bet 10-50 coins on your guess

**📊 Leaderboard:**
`/score` - Points leaderboard
`/coins` - Coins leaderboard

**🃏 Your Info:**
`/mycard` - See your role
`/status` - Game status

**⚡ Rules:**
• 30-second timer per guess
• Wrong guess = SWAP cards!
• Correct guess = Earn points + coins!

*Enjoy!* 🎉
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['game'])
def game_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = get_player_name(message.from_user)
    
    # Only works in groups
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    # Create game if doesn't exist
    if chat_id not in active_games:
        bot.reply_to(
            message,
            "🎮 **Create a new game!**\n\nChoose the number of players:",
            reply_markup=get_mode_buttons(),
            parse_mode='Markdown'
        )
        return
    
    game = active_games[chat_id]
    
    if game.status == "playing":
        bot.reply_to(message, "❌ Game already in progress!")
        return
    
    # Add player to existing game
    success, msg = game.add_player(user_id, user_name)
    bot.reply_to(message, msg)
    if success:
        save_game_data()
        # Show current players
        player_list = "\n".join([f"• {p['name']}" for p in game.players])
        bot.send_message(
            chat_id,
            f"👥 **Current Players ({len(game.players)}/{game.mode}):**\n\n{player_list}\n\n"
            f"👑 **Game Creator:** {game.creator_id}\n"
            f"🚀 `/start` to begin (Creator or Admin only)!",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['mode'])
def set_mode(message):
    chat_id = message.chat.id
    args = message.text.split()
    
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: /mode 4/6/8/10\nOr click the mode buttons with /game")
        return
    
    try:
        mode = int(args[1])
        if mode not in [4, 6, 8, 10]:
            bot.reply_to(message, "❌ Invalid mode! Choose 4, 6, 8, or 10.")
            return
        
        if chat_id in active_games and active_games[chat_id].status == "playing":
            bot.reply_to(message, "❌ Can't change mode during game! Use /reset first.")
            return
        
        active_games[chat_id] = Game(mode=mode, creator_id=message.from_user.id)
        bot.reply_to(
            message,
            f"✅ Mode set to {mode}-Player mode!\n"
            f"👑 Game Creator: {message.from_user.first_name}\n\n"
            f"📌 Use /game to join!\n"
            f"🚀 Use /start to begin the game (Creator or Admin only)!",
            parse_mode='Markdown'
        )
        save_game_data()
    except ValueError:
        bot.reply_to(message, "❌ Please enter a valid number!")

@bot.message_handler(commands=['bet'])
def place_bet(message):
    chat_id = message.chat.id
    player_id = message.from_user.id
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    if game.status != "playing":
        bot.reply_to(message, "❌ Game is not active!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, f"❌ Usage: /bet 10-{MAX_BET}")
        return
    
    try:
        bet_amount = int(args[1])
        if bet_amount < MIN_BET or bet_amount > MAX_BET:
            bot.reply_to(message, f"❌ Bet must be between {MIN_BET} and {MAX_BET} coins!")
            return
        
        player = game.get_player(player_id)
        if not player:
            bot.reply_to(message, "❌ You're not in this game!")
            return
        
        if player["coins"] < bet_amount:
            bot.reply_to(message, f"❌ You only have {player['coins']} coins!")
            return
        
        game.bets[player_id] = bet_amount
        bot.reply_to(message, f"💰 Bet placed: {bet_amount} coins on your success!\n💡 Click a button to guess!")
        
    except ValueError:
        bot.reply_to(message, "❌ Please enter a valid number!")

@bot.message_handler(commands=['score'])
def show_leaderboard(message):
    chat_id = message.chat.id
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    sorted_players = game.get_leaderboard()
    
    msg = "🏆 **POINTS LEADERBOARD** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(sorted_players):
        medal = medals[i] if i < 3 else f"{i+1}."
        role = game.get_player_role(p["id"])
        msg += f"{medal} {p['name']} - **{p['points']}** pts ({role})\n"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['coins'])
def show_coin_leaderboard(message):
    chat_id = message.chat.id
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    sorted_players = game.get_coin_leaderboard()
    
    msg = "💰 **COINS LEADERBOARD** 💰\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(sorted_players):
        medal = medals[i] if i < 3 else f"{i+1}."
        role = game.get_player_role(p["id"])
        msg += f"{medal} {p['name']} - **{p['coins']}** coins ({role})\n"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['mycard'])
def show_my_card(message):
    chat_id = message.chat.id
    player_id = message.from_user.id
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    role = game.get_player_role(player_id)
    player = game.get_player(player_id)
    
    if player:
        msg = f"🃏 **Your Role:** {role}\n"
        msg += f"💰 **Coins:** {player['coins']}\n"
        msg += f"⭐ **Points:** {player['points']}"
        bot.reply_to(message, msg, parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ You're not in this game!")

@bot.message_handler(commands=['status'])
def show_status(message):
    chat_id = message.chat.id
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    status = game.get_status()
    
    msg = f"📊 **GAME STATUS**\n\n{status}\n\n"
    msg += f"👥 **Players:** {len(game.players)}/{game.mode}\n"
    
    if game.status == "playing":
        seeker = game.get_current_seeker()
        if seeker:
            msg += f"👑 **Seeker:** {seeker['name']}\n"
        msg += f"🎯 **Target:** {game.get_target_role()}\n"
        msg += f"⭐ **Points:** {game.get_points()}\n"
        msg += f"⏱️ **Timer:** {TIMER_SECONDS}s\n"
        msg += f"\n💡 Click a button to guess!"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['reset'])
def reset_game(message):
    chat_id = message.chat.id
    if not is_admin_or_creator(message, active_games.get(chat_id)):
        bot.reply_to(message, "❌ Only admin or creator can reset!")
        return
    
    if chat_id in active_games:
        del active_games[chat_id]
        if chat_id in game_timers:
            del game_timers[chat_id]
        bot.reply_to(message, "✅ Game reset successfully! Use /game to start new game.")
        save_game_data()
    else:
        bot.reply_to(message, "❌ No game to reset!")

@bot.message_handler(commands=['end'])
def end_game(message):
    chat_id = message.chat.id
    if not is_admin_or_creator(message, active_games.get(chat_id)):
        bot.reply_to(message, "❌ Only admin or creator can end!")
        return
    
    if chat_id in active_games:
        active_games[chat_id].status = "ended"
        bot.reply_to(message, "🏁 **Game Ended!** Final Results:", parse_mode='Markdown')
        show_leaderboard(message)
        show_coin_leaderboard(message)
        save_game_data()
    else:
        bot.reply_to(message, "❌ No game to end!")

@bot.message_handler(commands=['players'])
def show_players(message):
    chat_id = message.chat.id
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    msg = "👥 **Players:**\n\n"
    for i, p in enumerate(game.players, 1):
        role = game.get_player_role(p["id"])
        msg += f"{i}. {p['name']} - {role if game.status != 'waiting' else '🔒 Hidden'}\n"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['history'])
def show_history(message):
    chat_id = message.chat.id
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    if not game.swap_history:
        bot.reply_to(message, "📋 No swaps yet!")
        return
    
    msg = "🔄 **Swap History:**\n\n"
    for i, swap in enumerate(game.swap_history[-10:], 1):
        msg += f"{i}. {swap['seeker']} → {swap['chosen']}\n   {swap['swapped']}\n"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

# ===== BOT OWNER COMMANDS =====

@bot.message_handler(commands=['addcoins'])
def add_coins(message):
    if not is_bot_owner(message):
        bot.reply_to(message, "❌ Only Bot Owner can use this!")
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: /addcoins @player amount")
        return
    
    target_name = args[1].replace('@', '').strip()
    try:
        amount = int(args[2])
    except:
        bot.reply_to(message, "❌ Please enter a valid number!")
        return
    
    chat_id = message.chat.id
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    target = None
    for p in game.players:
        if p["name"].lower() == target_name.lower():
            target = p
            break
    
    if not target:
        bot.reply_to(message, f"❌ Player '{target_name}' not found!")
        return
    
    target["coins"] += amount
    bot.reply_to(message, f"✅ Added {amount} coins to {target['name']}! New balance: {target['coins']}")
    save_game_data()

@bot.message_handler(commands=['removecoins'])
def remove_coins(message):
    if not is_bot_owner(message):
        bot.reply_to(message, "❌ Only Bot Owner can use this!")
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: /removecoins @player amount")
        return
    
    target_name = args[1].replace('@', '').strip()
    try:
        amount = int(args[2])
    except:
        bot.reply_to(message, "❌ Please enter a valid number!")
        return
    
    chat_id = message.chat.id
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    target = None
    for p in game.players:
        if p["name"].lower() == target_name.lower():
            target = p
            break
    
    if not target:
        bot.reply_to(message, f"❌ Player '{target_name}' not found!")
        return
    
    if target["coins"] < amount:
        bot.reply_to(message, f"❌ {target['name']} only has {target['coins']} coins!")
        return
    
    target["coins"] -= amount
    bot.reply_to(message, f"✅ Removed {amount} coins from {target['name']}! New balance: {target['coins']}")
    save_game_data()

@bot.message_handler(commands=['kick'])
def kick_player(message):
    if not is_admin_or_creator(message, active_games.get(message.chat.id)):
        bot.reply_to(message, "❌ Only admin or creator can kick players!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: /kick @player")
        return
    
    target_name = args[1].replace('@', '').strip()
    chat_id = message.chat.id
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    target = None
    for p in game.players:
        if p["name"].lower() == target_name.lower():
            target = p
            break
    
    if not target:
        bot.reply_to(message, f"❌ Player '{target_name}' not found!")
        return
    
    if target["id"] == BOT_OWNER_ID:
        bot.reply_to(message, "❌ Cannot kick Bot Owner!")
        return
    
    game.players.remove(target)
    if target["id"] in game.card_map:
        del game.card_map[target["id"]]
    
    bot.reply_to(message, f"✅ {target['name']} has been kicked from the game!")
    save_game_data()

# ===== WEBHOOK FOR RENDER =====

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index():
    return '🤖 Raja Rani Bot is running!', 200

# ===== START BOT =====

if __name__ == '__main__':
    print("🤖 RAJA RANI BOT STARTED!")
    print("📡 Running on Render...")
    
    data = load_game_data()
    print(f"📂 Loaded {len(data['games'])} saved games")
    
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL + '/' + BOT_TOKEN)
        print(f"✅ Webhook set to: {WEBHOOK_URL}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
