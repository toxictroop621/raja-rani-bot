import os
import random
import time
import threading
import json
from datetime import datetime
import telebot
from flask import Flask, request
from config import BOT_TOKEN, BOT_OWNER_ID, TIMER_SECONDS, MODES, STARTING_COINS, MIN_BET, MAX_BET

# ===== INITIALIZATION =====
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ===== GAME STORAGE =====
active_games = {}
game_history = {}

# ===== HELPER FUNCTIONS =====

def is_admin(message):
    if message.from_user.id == BOT_OWNER_ID:
        return True
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
                "swap_history": game.swap_history
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

# ===== GAME CLASS =====

class Game:
    def __init__(self, mode=4):
        self.mode = mode
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
        
    def add_player(self, player_id, player_name):
        if len(self.players) >= self.mode:
            return False, f"❌ Maximum {self.mode} players reached!"
        if player_id in [p["id"] for p in self.players]:
            return False, "❌ You're already in the game!"
        
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
            # ✅ CORRECT GUESS
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
            # ❌ WRONG GUESS - SWAP CARDS
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
            
            # New seeker after swap (the one who got the seeker role)
            new_seeker = self.get_current_seeker()
            return True, {
                "result": "wrong",
                "message": f"❌ WRONG! {seeker['name']} pointed at {chosen_player['name']} (had {chosen_role}) {bet_msg}",
                "swap": f"🔄 Swapped: {old_seeker_role} ↔ {old_chosen_role}",
                "new_seeker": new_seeker["name"] if new_seeker else "Unknown",
                "target": self.targets[self.current_level],
                "points": self.points[self.current_level]
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
            return f"🎯 Level {self.current_level+1}/{len(self.targets)}: {seeker['name']} is searching for {target} (+{points} points)"
        else:
            return "🏁 Game Over!"
    
    def get_leaderboard(self):
        return sorted(self.players, key=lambda x: x["points"], reverse=True)
    
    def get_coin_leaderboard(self):
        return sorted(self.players, key=lambda x: x["coins"], reverse=True)

# ===== BOT COMMANDS =====

@bot.message_handler(commands=['start', 'help'])
def send_help(message):
    help_text = """
🎮 **RAJA RANI BOT** 🎮

**👋 Welcome!**

📌 **How to Play:**
1. `/join` - Join the game
2. `/mode 4/6/8/10` - Choose mode
3. `/begin` - Start game (admin)
4. `/point @player` - Guess target
5. `/bet X` - Bet coins (10-50)
6. `/score` - Points leaderboard
7. `/coins` - Coins leaderboard
8. `/mycard` - See your role
9. `/status` - Game status

**⚡ Rules:**
• NO TIMER - Take your time!
• Correct guess = Earn points + Move to next level
• Wrong guess = SWAP cards with chosen player
• After swap, NEW seeker continues searching

**🔐 Admin:** Group admins can manage the game

*Enjoy!* 🎉
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['join'])
def join_game(message):
    chat_id = message.chat.id
    player_id = message.from_user.id
    player_name = get_player_name(message.from_user)
    
    if chat_id not in active_games:
        active_games[chat_id] = Game(mode=4)
    
    game = active_games[chat_id]
    success, msg = game.add_player(player_id, player_name)
    bot.reply_to(message, msg)
    if success:
        save_game_data()

@bot.message_handler(commands=['mode'])
def set_mode(message):
    chat_id = message.chat.id
    args = message.text.split()
    
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: /mode 4/6/8/10")
        return
    
    try:
        mode = int(args[1])
        if mode not in [4, 6, 8, 10]:
            bot.reply_to(message, "❌ Invalid mode! Choose 4, 6, 8, or 10.")
            return
        
        if chat_id in active_games and active_games[chat_id].status == "playing":
            bot.reply_to(message, "❌ Can't change mode during game! Use /reset first.")
            return
        
        active_games[chat_id] = Game(mode=mode)
        bot.reply_to(message, f"✅ Mode set to {mode}-Player mode! Use /join to join.")
        save_game_data()
    except ValueError:
        bot.reply_to(message, "❌ Please enter a valid number!")

@bot.message_handler(commands=['begin'])
def begin_game(message):
    chat_id = message.chat.id
    
    if not is_admin(message):
        bot.reply_to(message, "❌ Only group admin can start the game!")
        return
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No game found! Use /join first.")
        return
    
    game = active_games[chat_id]
    success, result = game.start_game()
    
    if success:
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
        
        bot.reply_to(
            message, 
            f"{result['message']}\n\n"
            f"👑 **Seeker:** {result['seeker']['name']}\n"
            f"🎯 **Target:** {result['target']}\n"
            f"⭐ **Points:** {result['points']}\n\n"
            f"💡 Type `/point @player` to guess!",
            parse_mode='Markdown'
        )
        
        save_game_data()
    else:
        bot.reply_to(message, f"❌ {result}")

@bot.message_handler(commands=['point'])
def make_guess(message):
    chat_id = message.chat.id
    player_id = message.from_user.id
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    if game.status != "playing":
        bot.reply_to(message, "❌ Game is not active! Use /begin to start.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: /point @player\nExample: /point @John")
        return
    
    target_name = args[1].replace('@', '').strip()
    target_player = None
    for p in game.players:
        if p["name"].lower() == target_name.lower():
            target_player = p
            break
    
    if not target_player:
        bot.reply_to(message, f"❌ Player '{target_name}' not found!")
        return
    
    success, result = game.make_guess(player_id, target_player["id"])
    
    if success:
        if result["result"] == "correct":
            if result.get("game_over"):
                bot.reply_to(message, f"🎉🏆 **{result['message']}**", parse_mode='Markdown')
                show_leaderboard(message)
                show_coin_leaderboard(message)
                save_game_data()
            else:
                bot.reply_to(
                    message,
                    f"{result['message']}\n\n"
                    f"👑 **Next Seeker:** {result['next_seeker']}\n"
                    f"🎯 **Target:** {result['next_target']}\n"
                    f"⭐ **Points:** {result['next_points']}",
                    parse_mode='Markdown'
                )
                save_game_data()
        else:
            bot.reply_to(
                message,
                f"{result['message']}\n{result['swap']}\n\n"
                f"👑 **New Seeker:** {result['new_seeker']}\n"
                f"🎯 **Target:** {result['target']}\n"
                f"⭐ **Points:** {result['points']}\n\n"
                f"💡 Continue guessing!",
                parse_mode='Markdown'
            )
            save_game_data()
    else:
        bot.reply_to(message, f"❌ {result}")

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
        bot.reply_to(message, f"💰 Bet placed: {bet_amount} coins on your success!\n💡 Type /point @player to guess!")
        
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
        msg += f"⏱️ **Timer:** No timer! Take your time!"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['reset'])
def reset_game(message):
    chat_id = message.chat.id
    if not is_admin(message):
        bot.reply_to(message, "❌ Only admin can reset!")
        return
    
    if chat_id in active_games:
        del active_games[chat_id]
        bot.reply_to(message, "✅ Game reset successfully! Use /join to start new game.")
        save_game_data()
    else:
        bot.reply_to(message, "❌ No game to reset!")

@bot.message_handler(commands=['end'])
def end_game(message):
    chat_id = message.chat.id
    if not is_admin(message):
        bot.reply_to(message, "❌ Only admin can end!")
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

@bot.message_handler(commands=['setcoins'])
def set_coins(message):
    if not is_bot_owner(message):
        bot.reply_to(message, "❌ Only Bot Owner can use this!")
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: /setcoins @player amount")
        return
    
    target_name = args[1].replace('@', '').strip()
    try:
        amount = int(args[2])
        if amount < 0:
            bot.reply_to(message, "❌ Amount cannot be negative!")
            return
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
    
    target["coins"] = amount
    bot.reply_to(message, f"✅ Set {target['name']}'s coins to {amount}!")
    save_game_data()

@bot.message_handler(commands=['resetcoins'])
def reset_all_coins(message):
    if not is_bot_owner(message):
        bot.reply_to(message, "❌ Only Bot Owner can use this!")
        return
    
    chat_id = message.chat.id
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    for p in game.players:
        p["coins"] = STARTING_COINS
    
    bot.reply_to(message, f"✅ Reset all players to {STARTING_COINS} coins!")
    save_game_data()

@bot.message_handler(commands=['kick'])
def kick_player(message):
    if not is_admin(message):
        bot.reply_to(message, "❌ Only admin can kick players!")
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
