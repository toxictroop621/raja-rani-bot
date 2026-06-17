import os
import random
import time
import threading
import json
import re
from datetime import datetime, timedelta
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask, request
from config import BOT_TOKEN, BOT_OWNER_ID, TIMER_SECONDS, MODES, STARTING_COINS, MIN_BET, MAX_BET

# ===== INITIALIZATION =====
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ===== SET COMMAND SUGGESTIONS =====

def set_bot_commands():
    commands = [
        BotCommand("game", "⚔️ Create or join a game"),
        BotCommand("join", "👋 Join existing game"),
        BotCommand("mode", "📊 Choose player count (4/6/8/10)"),
        BotCommand("startgame", "🚀 Start game"),
        BotCommand("bet", "💰 Bet coins on your guess"),
        BotCommand("score", "🏆 View points leaderboard"),
        BotCommand("coins", "💰 View coins leaderboard"),
        BotCommand("mycard", "🃏 View your role & stats"),
        BotCommand("status", "📊 View game status"),
        BotCommand("players", "👥 View all players"),
        BotCommand("history", "🔄 View swap history"),
        BotCommand("daily", "🎁 Claim daily bonus"),
        BotCommand("profile", "👤 View your profile & achievements"),
    ]
    bot.set_my_commands(commands)
    print("✅ Bot commands set!")

set_bot_commands()

# ===== GAME STORAGE =====
active_games = {}
game_timers = {}
game_history = {}
player_data = {}
user_database = {}  # Stores ALL users who ever interacted

# ===== ACHIEVEMENTS / BADGES =====

ACHIEVEMENTS = {
    "first_win": {"name": "🥇 First Blood", "desc": "Win your first game"},
    "champion": {"name": "🏆 Champion", "desc": "Win 5 games"},
    "king": {"name": "👑 King", "desc": "Win 10 games"},
    "sharpshooter": {"name": "🎯 Sharpshooter", "desc": "Guess correctly 5 times in a row"},
    "master_swapper": {"name": "🔄 Master Swapper", "desc": "Survive 5 swaps"},
    "rich": {"name": "💰 Rich", "desc": "Collect 500 coins"},
    "detective": {"name": "🕵️ Detective", "desc": "Guess correctly without any hints"},
    "streak_3": {"name": "🔥 Hot Streak", "desc": "3 correct guesses in a row"},
    "streak_5": {"name": "⭐ Legendary", "desc": "5 correct guesses in a row"},
    "player": {"name": "🎮 Player", "desc": "Play 10 games"},
}

# ============================================================
# USER DATABASE FUNCTIONS (Built-in)
# ============================================================

def load_user_database():
    try:
        with open("user_database.json", "r") as f:
            return json.load(f)
    except:
        return {}

def save_user_database():
    try:
        with open("user_database.json", "w") as f:
            json.dump(user_database, f, indent=2)
    except:
        pass

def register_user(user_id, username, first_name, last_name=""):
    global user_database
    user_id_str = str(user_id)
    
    if user_id_str not in user_database:
        user_database[user_id_str] = {
            "id": user_id,
            "username": username or "",
            "first_name": first_name or "",
            "last_name": last_name or "",
            "registered_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat()
        }
        save_user_database()
        return True
    else:
        user_database[user_id_str]["last_active"] = datetime.now().isoformat()
        if username:
            user_database[user_id_str]["username"] = username
        save_user_database()
        return False

def find_user_by_name_or_username(search_term):
    global user_database
    search_term = search_term.replace('@', '').strip().lower()
    
    if not user_database:
        return None, None
    
    for uid, data in user_database.items():
        if data.get("username", "").lower() == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    for uid, data in user_database.items():
        if data.get("first_name", "").lower() == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    for uid, data in user_database.items():
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip().lower()
        if full_name == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    for uid, data in user_database.items():
        first_name = data.get("first_name", "").lower()
        username = data.get("username", "").lower()
        if search_term in first_name or search_term in username:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    return None, None

# ============================================================
# PLAYER STATS FUNCTIONS (Built-in)
# ============================================================

def get_player_stats(player_id):
    if str(player_id) not in player_data:
        player_data[str(player_id)] = {
            "coins": STARTING_COINS,
            "points": 0,
            "wins": 0,
            "games": 0,
            "streak": 0,
            "correct_guesses": 0,
            "wrong_guesses": 0,
            "swaps_survived": 0,
            "last_daily": None,
            "badges": [],
            "total_correct": 0,
            "name": None
        }
        save_player_data()
    return player_data[str(player_id)]

def save_player_data():
    try:
        with open("player_data.json", "w") as f:
            json.dump(player_data, f, indent=2)
    except:
        pass

def load_player_data():
    try:
        with open("player_data.json", "r") as f:
            return json.load(f)
    except:
        return {}

def check_achievements(player_id):
    stats = get_player_stats(player_id)
    new_badges = []
    
    if stats["wins"] >= 1 and "first_win" not in stats["badges"]:
        stats["badges"].append("first_win")
        new_badges.append("🥇 First Blood")
    
    if stats["wins"] >= 5 and "champion" not in stats["badges"]:
        stats["badges"].append("champion")
        new_badges.append("🏆 Champion")
    
    if stats["wins"] >= 10 and "king" not in stats["badges"]:
        stats["badges"].append("king")
        new_badges.append("👑 King")
    
    if stats["total_correct"] >= 5 and "sharpshooter" not in stats["badges"]:
        stats["badges"].append("sharpshooter")
        new_badges.append("🎯 Sharpshooter")
    
    if stats["swaps_survived"] >= 5 and "master_swapper" not in stats["badges"]:
        stats["badges"].append("master_swapper")
        new_badges.append("🔄 Master Swapper")
    
    if stats["coins"] >= 500 and "rich" not in stats["badges"]:
        stats["badges"].append("rich")
        new_badges.append("💰 Rich")
    
    if stats["games"] >= 10 and "player" not in stats["badges"]:
        stats["badges"].append("player")
        new_badges.append("🎮 Player")
    
    if stats["streak"] >= 3 and "streak_3" not in stats["badges"]:
        stats["badges"].append("streak_3")
        new_badges.append("🔥 Hot Streak")
    
    if stats["streak"] >= 5 and "streak_5" not in stats["badges"]:
        stats["badges"].append("streak_5")
        new_badges.append("⭐ Legendary")
    
    if new_badges:
        save_player_data()
    
    return new_badges

# ============================================================
# GAME DATA FUNCTIONS (Built-in)
# ============================================================

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
                "creator_id": game.creator_id,
                "found_players": game.found_players
            }
        with open("game_data.json", "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass

def load_game_data():
    try:
        with open("game_data.json", "r") as f:
            return json.load(f)
    except:
        return {"games": {}, "history": {}}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_admin_or_creator(message, game):
    if message.from_user.id == BOT_OWNER_ID:
        return True
    if game and game.creator_id == message.from_user.id:
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

def check_dm_access(player_id):
    try:
        bot.send_chat_action(player_id, 'typing')
        return True
    except:
        return False

def delete_message(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

# ============================================================
# FIND PLAYER - Works with user_database
# ============================================================

def find_player_by_name(target_name):
    target_name = target_name.replace('@', '').strip().lower()
    
    # 1. Search in active games
    for chat_id, game in active_games.items():
        for p in game.players:
            if p["name"].lower() == target_name:
                return p["id"], p["name"], True
    
    # 2. Search in user_database
    user_id, display_name = find_user_by_name_or_username(target_name)
    if user_id:
        return user_id, display_name, False
    
    # 3. Search in player_data
    for pid, stats in player_data.items():
        stored_name = stats.get("name", "")
        if stored_name.lower() == target_name:
            return int(pid), stored_name, False
    
    return None, None, False

# ============================================================
# INLINE KEYBOARD FUNCTIONS
# ============================================================

def get_player_buttons(game, seeker_id, chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = []
    
    active_players = []
    for p in game.players:
        if p["id"] == seeker_id:
            continue
        if p["id"] in game.found_players:
            continue
        active_players.append(p)
    
    if not active_players:
        return None
    
    for p in active_players:
        buttons.append(InlineKeyboardButton(
            f"👤 {p['name']}", 
            callback_data=f"guess_{chat_id}_{p['id']}_{seeker_id}"
        ))
    
    buttons.append(InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{chat_id}"))
    markup.add(*buttons)
    return markup

# ============================================================
# GAME CLASS
# ============================================================

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
        self.start_message_id = None
        self.found_players = []
        self.current_seeker_streak = {}
        
    def add_player(self, player_id, player_name):
        if len(self.players) >= self.mode:
            return False, f"❌ Maximum {self.mode} players reached!"
        if player_id in [p["id"] for p in self.players]:
            return False, "❌ You're already in the game!"
        
        if not check_dm_access(player_id):
            return False, f"❌ {player_name}, please start the bot in DM first!"
        
        self.players.append({
            "id": player_id, 
            "name": player_name, 
            "coins": STARTING_COINS, 
            "points": 0,
            "joined_at": datetime.now().isoformat()
        })
        
        stats = get_player_stats(player_id)
        stats["name"] = player_name
        save_player_data()
        
        return True, f"✅ {player_name} joined! ({len(self.players)}/{self.mode})"
    
    def start_game(self):
        if len(self.players) < 4:
            return False, f"❌ Need at least 4 players! ({len(self.players)} currently)"
        if len(self.players) != self.mode:
            return False, f"❌ This mode needs {self.mode} players! {len(self.players)} joined."
        
        for p in self.players:
            if not check_dm_access(p["id"]):
                return False, f"❌ {p['name']} hasn't started the bot in DM!"
        
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
        self.found_players = []
        self.current_seeker_streak = {}
        
        seeker = self.get_current_seeker()
        target = self.get_target_role()
        
        return True, {
            "message": f"⚔️ Game started! {len(self.players)} players, {self.mode}-Player Mode",
            "seeker": seeker,
            "target": target,
            "points": self.get_points()
        }
    
    def get_current_seeker(self):
        if self.current_level >= len(self.roles):
            return None
        role = self.roles[self.current_level]
        for player in self.players:
            if self.card_map.get(player["id"]) == role:
                return player
        return None
    
    def get_target_role(self):
        if self.current_level < len(self.targets):
            return self.targets[self.current_level]
        return None
    
    def get_points(self):
        if self.current_level < len(self.points):
            return self.points[self.current_level]
        return 0
    
    def get_active_players(self):
        return [p for p in self.players if p["id"] not in self.found_players]
    
    def make_guess(self, seeker_id, chosen_player_id):
        if self.status != "playing":
            return False, "❌ Game is not active!"
        
        seeker = self.get_current_seeker()
        if not seeker or seeker["id"] != seeker_id:
            return False, "❌ It's not your turn!"
        
        target_role = self.get_target_role()
        if not target_role:
            return False, "❌ No target found!"
        
        chosen_role_full = self.card_map.get(chosen_player_id, "Unknown")
        chosen_role_plain = re.sub(r'[^\w\s]', '', chosen_role_full).strip()
        
        chosen_player = self.get_player(chosen_player_id)
        if not chosen_player:
            return False, "❌ Player not found!"
        
        bet_amount = self.bets.get(seeker_id, 0)
        
        if chosen_role_plain == target_role:
            points = self.get_points()
            seeker["points"] += points
            
            stats = get_player_stats(seeker_id)
            stats["points"] += points
            stats["total_correct"] += 1
            stats["streak"] += 1
            stats["correct_guesses"] += 1
            
            if seeker["id"] not in self.found_players:
                self.found_players.append(seeker["id"])
            
            if bet_amount > 0:
                seeker["coins"] += bet_amount * 2
                stats["coins"] += bet_amount * 2
                bet_msg = f"💰 Won {bet_amount * 2} coins!"
            else:
                bet_msg = ""
            
            self.current_level += 1
            
            if self.current_level >= len(self.targets):
                self.status = "ended"
                stats["wins"] += 1
                stats["games"] += 1
                save_player_data()
                new_badges = check_achievements(seeker_id)
                badge_msg = ""
                if new_badges:
                    badge_msg = f"\n\n🎖️ **New Achievement{'s' if len(new_badges) > 1 else ''} Unlocked:**\n" + "\n".join([f"• {b}" for b in new_badges])
                
                return True, {
                    "result": "correct",
                    "message": f"🎉🏆 {seeker['name']} found {target_role}! GAME OVER! Winner: {seeker['name']} with {seeker['points']} points! {bet_msg}{badge_msg}",
                    "points": points,
                    "game_over": True
                }
            else:
                next_seeker = self.get_current_seeker()
                save_player_data()
                new_badges = check_achievements(seeker_id)
                badge_msg = ""
                if new_badges:
                    badge_msg = f"\n\n🎖️ **New Achievement{'s' if len(new_badges) > 1 else ''} Unlocked:**\n" + "\n".join([f"• {b}" for b in new_badges])
                
                return True, {
                    "result": "correct",
                    "message": f"✅ {seeker['name']} found {target_role}! +{points} points! 🎉 {bet_msg}{badge_msg}",
                    "points": points,
                    "next_seeker": next_seeker["name"] if next_seeker else "Unknown",
                    "next_target": self.get_target_role(),
                    "next_points": self.get_points(),
                    "found_players": self.found_players.copy()
                }
        else:
            old_seeker_role = self.card_map[seeker_id]
            old_chosen_role = self.card_map[chosen_player_id]
            
            self.card_map[seeker_id] = old_chosen_role
            self.card_map[chosen_player_id] = old_seeker_role
            
            stats = get_player_stats(seeker_id)
            stats["wrong_guesses"] += 1
            stats["streak"] = 0
            stats["swaps_survived"] += 1
            save_player_data()
            
            if bet_amount > 0:
                seeker["coins"] -= bet_amount
                stats["coins"] -= bet_amount
                bet_msg = f"💰 Lost {bet_amount} coins!"
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
                "message": f"❌ WRONG! {seeker['name']} pointed at {chosen_player['name']} (had {chosen_role_full}) {bet_msg}",
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
            return f"⏳ Waiting... ({len(self.players)}/{self.mode})"
        elif self.status == "playing":
            seeker = self.get_current_seeker()
            target = self.get_target_role()
            points = self.get_points()
            active_count = len(self.get_active_players())
            return f"🎯 Level {self.current_level+1}/{len(self.targets)}: {seeker['name'] if seeker else 'Unknown'} → {target} (+{points} pts)\n👥 Active players left: {active_count}"
        else:
            return "🏁 Game Over!"
    
    def get_leaderboard(self):
        return sorted(self.players, key=lambda x: x["points"], reverse=True)
    
    def get_coin_leaderboard(self):
        return sorted(self.players, key=lambda x: x["coins"], reverse=True)

# ============================================================
# CALLBACK HANDLERS
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('guess_'))
def handle_guess(call):
    try:
        _, chat_id_str, chosen_id_str, seeker_id_str = call.data.split('_')
        chat_id = int(chat_id_str)
        chosen_id = int(chosen_id_str)
        seeker_id = int(seeker_id_str)
        
        user_id = call.from_user.id
        
        if user_id != seeker_id:
            bot.answer_callback_query(call.id, "❌ Not your turn!", show_alert=True)
            return
        
        if chat_id not in active_games:
            bot.answer_callback_query(call.id, "❌ No active game!", show_alert=True)
            return
        
        game = active_games[chat_id]
        
        if game.status != "playing":
            bot.answer_callback_query(call.id, "❌ Game is not active!", show_alert=True)
            return
        
        if chosen_id in game.found_players:
            bot.answer_callback_query(call.id, "❌ This player already found their target!", show_alert=True)
            return
        
        if chosen_id == seeker_id:
            bot.answer_callback_query(call.id, "❌ You can't guess yourself!", show_alert=True)
            return
        
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
                    buttons = get_player_buttons(game, next_seeker["id"], chat_id)
                    if buttons:
                        active_count = len(game.get_active_players())
                        bot.send_message(
                            chat_id,
                            f"{result['message']}\n\n"
                            f"👑 **Next Seeker:** {next_seeker['name']}\n"
                            f"🎯 **Target:** {result['next_target']}\n"
                            f"⭐ **Points:** {result['next_points']}\n"
                            f"👥 **Active Players:** {active_count}\n\n"
                            f"💡 Click a button to guess!",
                            reply_markup=buttons,
                            parse_mode='Markdown'
                        )
                        save_game_data()
                    else:
                        bot.send_message(chat_id, "❌ No active players left!")
                        game.status = "ended"
                        save_game_data()
            else:
                new_seeker = game.get_current_seeker()
                buttons = get_player_buttons(game, new_seeker["id"], chat_id)
                if buttons:
                    bot.send_message(
                        chat_id,
                        f"{result['message']}\n{result['swap']}\n\n"
                        f"👑 **New Seeker:** {new_seeker['name']}\n\n"
                        f"💡 Click a button to guess!",
                        reply_markup=buttons,
                        parse_mode='Markdown'
                    )
                    save_game_data()
                else:
                    bot.send_message(chat_id, "❌ No active players left!")
                    game.status = "ended"
                    save_game_data()
            
            bot.answer_callback_query(call.id, "✅ Done!")
        else:
            bot.answer_callback_query(call.id, f"❌ {result}", show_alert=True)
            
    except Exception as e:
        print(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def handle_cancel(call):
    chat_id = int(call.data.split('_')[1])
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    bot.answer_callback_query(call.id, "❌ Cancelled")

# ============================================================
# SHOW LEADERBOARD FUNCTION
# ============================================================

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

# ============================================================
# BOT COMMANDS
# ============================================================

@bot.message_handler(commands=['start'])
def start_command(message):
    global user_database
    user = message.from_user
    register_user(user.id, user.username, user.first_name, user.last_name or "")
    
    help_text = """
⚔️ **CARD WARFARE BOT** ⚔️

📌 **Game Commands:**
`/game` - Create or join a game
`/join` - Join existing game
`/mode 4/6/8/10` - Choose player count
`/startgame` - Start game
`/bet X` - Bet 10-50 coins

📊 **Info Commands:**
`/score` - Points leaderboard
`/coins` - Coins leaderboard  
`/mycard` - Your role & stats
`/status` - Game status
`/players` - List players
`/history` - Swap history

🎁 **Rewards:**
`/daily` - Claim daily bonus (25 coins)
`/profile` - View your profile & achievements

⚡ **Rules:**
• Wrong guess = SWAP cards!
• Correct guess = Earn points!
• Found players are removed from next rounds

*Enjoy!* 🎉
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['game'])
def game_command(message):
    chat_id = message.chat.id
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    user_id = message.from_user.id
    
    if chat_id not in active_games:
        active_games[chat_id] = Game(mode=4, creator_id=user_id)
        bot.reply_to(
            message, 
            "⚔️ **Game created!**\n\n"
            "📌 Default mode: 4 Players\n"
            "🔄 Use `/mode 4/6/8/10` to change\n"
            "👋 Use `/join` to join!\n"
            "🚀 Use `/startgame` to begin!",
            parse_mode='Markdown'
        )
        save_game_data()
    else:
        game = active_games[chat_id]
        if game.status == "playing":
            bot.reply_to(message, "❌ Game already in progress!")
            return
        
        player_list = "\n".join([f"• {p['name']}" for p in game.players]) if game.players else "No players yet"
        bot.send_message(
            chat_id,
            f"⚔️ **Game Menu**\n\n"
            f"📌 Mode: {game.mode}-Player\n"
            f"👥 Players: {len(game.players)}/{game.mode}\n\n"
            f"{player_list}\n\n"
            f"👋 Use `/join` to join!\n"
            f"🚀 Use `/startgame` to begin!",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['join'])
def join_game(message):
    global user_database
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = get_player_name(message.from_user)
    
    user = message.from_user
    register_user(user.id, user.username, user.first_name, user.last_name or "")
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No game! Use `/game` to create one.", parse_mode='Markdown')
        return
    
    game = active_games[chat_id]
    
    if game.status == "playing":
        bot.reply_to(message, "❌ Game already in progress!")
        return
    
    success, msg = game.add_player(user_id, user_name)
    bot.reply_to(message, msg)
    
    if success:
        save_game_data()
        player_list = "\n".join([f"• {p['name']}" for p in game.players])
        bot.send_message(
            chat_id,
            f"👥 **Players ({len(game.players)}/{game.mode}):**\n\n{player_list}\n\n"
            f"🚀 Use `/startgame` to begin!",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['mode'])
def set_mode(message):
    chat_id = message.chat.id
    args = message.text.split()
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/mode 4/6/8/10`", parse_mode='Markdown')
        return
    
    try:
        mode = int(args[1])
        if mode not in [4, 6, 8, 10]:
            bot.reply_to(message, "❌ Invalid mode! Choose 4, 6, 8, or 10.")
            return
        
        if chat_id in active_games and active_games[chat_id].status == "playing":
            bot.reply_to(message, "❌ Can't change mode during game! Use `/reset` first.", parse_mode='Markdown')
            return
        
        active_games[chat_id] = Game(mode=mode, creator_id=message.from_user.id)
        bot.reply_to(
            message,
            f"✅ Mode set to {mode}-Player mode!\n"
            f"👑 Creator: {message.from_user.first_name}\n\n"
            f"👋 Use `/join` to join!\n"
            f"🚀 Use `/startgame` to begin!",
            parse_mode='Markdown'
        )
        save_game_data()
    except ValueError:
        bot.reply_to(message, "❌ Please enter a valid number!")

@bot.message_handler(commands=['startgame'])
def start_game_command(message):
    chat_id = message.chat.id
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No game! Use `/game` to create one.", parse_mode='Markdown')
        return
    
    game = active_games[chat_id]
    
    if game.status != "waiting":
        bot.reply_to(message, "❌ Game already started or ended!")
        return
    
    if not is_admin_or_creator(message, game):
        bot.reply_to(message, "❌ Only the game creator or group admin can start the game!")
        return
    
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
        
        buttons = get_player_buttons(game, result['seeker']["id"], chat_id)
        if buttons:
            active_count = len(game.get_active_players())
            bot.send_message(
                chat_id, 
                f"⚔️ **GAME STARTED!**\n\n"
                f"👑 **Seeker:** {result['seeker']['name']}\n"
                f"🎯 **Target:** {result['target']}\n"
                f"⭐ **Points:** {result['points']}\n"
                f"👥 **Active Players:** {active_count}\n\n"
                f"💡 Click a button to guess!",
                reply_markup=buttons,
                parse_mode='Markdown'
            )
            save_game_data()
        else:
            bot.send_message(chat_id, "❌ No active players to guess!")
            game.status = "ended"
            save_game_data()
    else:
        bot.send_message(chat_id, f"❌ {result}")

@bot.message_handler(commands=['bet'])
def place_bet(message):
    chat_id = message.chat.id
    player_id = message.from_user.id
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    if game.status != "playing":
        bot.reply_to(message, "❌ Game is not active!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, f"❌ Usage: `/bet 10-{MAX_BET}`", parse_mode='Markdown')
        return
    
    try:
        bet_amount = int(args[1])
        if bet_amount < MIN_BET or bet_amount > MAX_BET:
            bot.reply_to(message, f"❌ Bet must be between {MIN_BET} and {MAX_BET}!")
            return
        
        player = game.get_player(player_id)
        if not player:
            bot.reply_to(message, "❌ You're not in this game!")
            return
        
        stats = get_player_stats(player_id)
        if stats["coins"] < bet_amount:
            bot.reply_to(message, f"❌ You only have {stats['coins']} coins!")
            return
        
        game.bets[player_id] = bet_amount
        bot.reply_to(message, f"💰 Bet placed: {bet_amount} coins!\n💡 Click a button to guess!")
        
    except ValueError:
        bot.reply_to(message, "❌ Enter a valid number!")

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
        status = "✅ Found" if p["id"] in game.found_players else "🔄 Active"
        msg += f"{medal} {p['name']} - **{p['points']}** pts ({role}) - {status}\n"
    
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
        status = "✅ Found" if player["id"] in game.found_players else "🔄 Active"
        msg = f"🃏 **Your Role:** {role}\n💰 **Coins:** {player['coins']}\n⭐ **Points:** {player['points']}\n📌 **Status:** {status}"
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
    active_count = len(game.get_active_players())
    msg += f"✅ **Found Players:** {len(game.found_players)}\n"
    msg += f"🔄 **Active Players:** {active_count}\n"
    
    if game.status == "playing":
        seeker = game.get_current_seeker()
        if seeker:
            msg += f"👑 **Seeker:** {seeker['name']}\n"
        msg += f"🎯 **Target:** {game.get_target_role()}\n"
        msg += f"⭐ **Points:** {game.get_points()}\n"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

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
        status = "✅ Found" if p["id"] in game.found_players else "🔄 Active"
        msg += f"{i}. {p['name']} - {role} - {status}\n"
    
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

# ============================================================
# DAILY REWARD
# ============================================================

@bot.message_handler(commands=['daily'])
def daily_reward(message):
    user_id = message.from_user.id
    stats = get_player_stats(user_id)
    
    last_daily = stats.get("last_daily")
    today = datetime.now().date()
    
    if last_daily:
        last_date = datetime.fromisoformat(last_daily).date()
        if last_date == today:
            bot.reply_to(message, "❌ You already claimed your daily reward today!\nCome back tomorrow for more coins! 🎁")
            return
    
    daily_amount = 25
    stats["coins"] += daily_amount
    stats["last_daily"] = datetime.now().isoformat()
    save_player_data()
    
    new_badges = check_achievements(user_id)
    badge_msg = ""
    if new_badges:
        badge_msg = f"\n\n🎖️ **New Achievement{'s' if len(new_badges) > 1 else ''} Unlocked:**\n" + "\n".join([f"• {b}" for b in new_badges])
    
    bot.reply_to(
        message,
        f"🎁 **Daily Reward Claimed!**\n\n"
        f"💰 You received **{daily_amount} coins**!\n"
        f"📊 Total coins: **{stats['coins']}**\n"
        f"⏰ Come back tomorrow for more!{badge_msg}",
        parse_mode='Markdown'
    )

# ============================================================
# PROFILE
# ============================================================

@bot.message_handler(commands=['profile'])
def profile_command(message):
    user_id = message.from_user.id
    user_name = get_player_name(message.from_user)
    stats = get_player_stats(user_id)
    
    badge_names = {
        "first_win": "🥇 First Blood",
        "champion": "🏆 Champion",
        "king": "👑 King",
        "sharpshooter": "🎯 Sharpshooter",
        "master_swapper": "🔄 Master Swapper",
        "rich": "💰 Rich",
        "detective": "🕵️ Detective",
        "streak_3": "🔥 Hot Streak",
        "streak_5": "⭐ Legendary",
        "player": "🎮 Player",
    }
    
    badges = stats.get("badges", [])
    badge_list = "\n".join([f"• {badge_names.get(b, b)}" for b in badges]) if badges else "No badges yet. Keep playing!"
    
    msg = f"""
👤 **Profile: {user_name}**

📊 **Stats:**
• Total Coins: **{stats['coins']}**
• Total Points: **{stats['points']}**
• Games Played: **{stats['games']}**
• Wins: **{stats['wins']}**
• Correct Guesses: **{stats['correct_guesses']}**
• Wrong Guesses: **{stats['wrong_guesses']}**
• Current Streak: **{stats['streak']}**
• Swaps Survived: **{stats['swaps_survived']}**

🎖️ **Achievements:**
{badge_list}

💡 Keep playing to unlock more achievements!
    """
    bot.reply_to(message, msg, parse_mode='Markdown')

# ============================================================
# ADMIN COMMANDS
# ============================================================

@bot.message_handler(commands=['stop'])
def stop_game(message):
    chat_id = message.chat.id
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    if chat_id not in active_games:
        bot.reply_to(message, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    if not is_admin_or_creator(message, game):
        bot.reply_to(message, "❌ Only admin/creator can stop!")
        return
    
    if game.status != "playing":
        bot.reply_to(message, "❌ Game is not active!")
        return
    
    game.status = "ended"
    bot.reply_to(message, "⏹️ **Game stopped!**", parse_mode='Markdown')
    show_leaderboard(message)
    save_game_data()

@bot.message_handler(commands=['reset'])
def reset_game(message):
    chat_id = message.chat.id
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    if not is_admin_or_creator(message, active_games.get(chat_id)):
        bot.reply_to(message, "❌ Only admin/creator can reset!")
        return
    
    if chat_id in active_games:
        del active_games[chat_id]
        if chat_id in game_timers:
            del game_timers[chat_id]
        bot.reply_to(message, "🔄 **Game reset!** Use `/game` to start new.", parse_mode='Markdown')
        save_game_data()
    else:
        bot.reply_to(message, "❌ No game to reset!")

@bot.message_handler(commands=['kick'])
def kick_player(message):
    chat_id = message.chat.id
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    if not is_admin_or_creator(message, active_games.get(chat_id)):
        bot.reply_to(message, "❌ Only admin/creator can kick!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/kick @player`", parse_mode='Markdown')
        return
    
    target_name = args[1].replace('@', '').strip()
    
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
    if target["id"] in game.found_players:
        game.found_players.remove(target["id"])
    
    bot.reply_to(message, f"✅ {target['name']} kicked from game!")
    save_game_data()

# ============================================================
# 🔐 SECRET ADMIN COMMANDS
# ============================================================

def get_badge_list():
    badge_list = ""
    for key, badge in ACHIEVEMENTS.items():
        badge_list += f"• `{key}` - {badge['name']}\n"
    return badge_list

@bot.message_handler(commands=['givecoins'])
def give_coins_secret(message):
    if not is_bot_owner(message):
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/givecoins @player amount`", parse_mode='Markdown')
        return
    
    target_name = args[1].replace('@', '').strip()
    try:
        amount = int(args[2])
    except:
        bot.reply_to(message, "❌ Please enter a valid number!")
        return
    
    target_id, target_name_found, in_game = find_player_by_name(target_name)
    
    if not target_id:
        bot.reply_to(
            message, 
            f"❌ Player '{target_name}' not found!\n\n"
            f"💡 Make sure they have:\n"
            f"• Used `/start` with the bot\n"
            f"• Or type their exact username: @username",
            parse_mode='Markdown'
        )
        return
    
    stats = get_player_stats(target_id)
    stats["coins"] += amount
    stats["name"] = target_name_found
    
    for chat_id, game in active_games.items():
        for p in game.players:
            if p["id"] == target_id:
                p["coins"] += amount
                break
    
    save_player_data()
    save_game_data()
    
    bot.reply_to(
        message,
        f"🔐 **Secret Admin Action**\n\n"
        f"✅ Added **{amount} coins** to **{target_name_found}**!\n"
        f"💰 New balance: **{stats['coins']}** coins",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['givebadge'])
def give_badge_secret(message):
    if not is_bot_owner(message):
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(
            message, 
            f"❌ Usage: `/givebadge @player badge_name`\n\nAvailable badges:\n{get_badge_list()}", 
            parse_mode='Markdown'
        )
        return
    
    target_name = args[1].replace('@', '').strip()
    badge_key = args[2].strip()
    
    if badge_key not in ACHIEVEMENTS:
        bot.reply_to(
            message,
            f"❌ Badge '{badge_key}' not found!\n\nAvailable badges:\n{get_badge_list()}",
            parse_mode='Markdown'
        )
        return
    
    target_id, target_name_found, in_game = find_player_by_name(target_name)
    
    if not target_id:
        bot.reply_to(
            message, 
            f"❌ Player '{target_name}' not found!\n\n"
            f"💡 Make sure they have used `/start` with the bot.",
            parse_mode='Markdown'
        )
        return
    
    stats = get_player_stats(target_id)
    stats["name"] = target_name_found
    
    if badge_key in stats["badges"]:
        bot.reply_to(message, f"❌ {target_name_found} already has **{ACHIEVEMENTS[badge_key]['name']}**!", parse_mode='Markdown')
        return
    
    stats["badges"].append(badge_key)
    save_player_data()
    
    bot.reply_to(
        message,
        f"🔐 **Secret Admin Action**\n\n"
        f"✅ Gave **{ACHIEVEMENTS[badge_key]['name']}** to **{target_name_found}**!\n"
        f"📋 {ACHIEVEMENTS[badge_key]['desc']}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['removebadge'])
def remove_badge_secret(message):
    if not is_bot_owner(message):
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/removebadge @player badge_name`", parse_mode='Markdown')
        return
    
    target_name = args[1].replace('@', '').strip()
    badge_key = args[2].strip()
    
    if badge_key not in ACHIEVEMENTS:
        bot.reply_to(message, f"❌ Badge '{badge_key}' not found!", parse_mode='Markdown')
        return
    
    target_id, target_name_found, in_game = find_player_by_name(target_name)
    
    if not target_id:
        bot.reply_to(
            message, 
            f"❌ Player '{target_name}' not found!\n\n"
            f"💡 Make sure they have used `/start` with the bot.",
            parse_mode='Markdown'
        )
        return
    
    stats = get_player_stats(target_id)
    stats["name"] = target_name_found
    
    if badge_key not in stats["badges"]:
        bot.reply_to(message, f"❌ {target_name_found} doesn't have **{ACHIEVEMENTS[badge_key]['name']}**!", parse_mode='Markdown')
        return
    
    stats["badges"].remove(badge_key)
    save_player_data()
    
    bot.reply_to(
        message,
        f"🔐 **Secret Admin Action**\n\n"
        f"✅ Removed **{ACHIEVEMENTS[badge_key]['name']}** from **{target_name_found}**!",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['listbadges'])
def list_badges_secret(message):
    if not is_bot_owner(message):
        return
    
    bot.reply_to(
        message,
        f"📋 **Available Badges**\n\n{get_badge_list()}\n\n"
        f"Usage: `/givebadge @player badge_key`\n"
        f"Example: `/givebadge @John king`",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['resetplayer'])
def reset_player_secret(message):
    if not is_bot_owner(message):
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/resetplayer @player`", parse_mode='Markdown')
        return
    
    target_name = args[1].replace('@', '').strip()
    
    target_id, target_name_found, in_game = find_player_by_name(target_name)
    
    if not target_id:
        bot.reply_to(
            message, 
            f"❌ Player '{target_name}' not found!\n\n"
            f"💡 Make sure they have used `/start` with the bot.",
            parse_mode='Markdown'
        )
        return
    
    player_data[str(target_id)] = {
        "coins": STARTING_COINS,
        "points": 0,
        "wins": 0,
        "games": 0,
        "streak": 0,
        "correct_guesses": 0,
        "wrong_guesses": 0,
        "swaps_survived": 0,
        "last_daily": None,
        "badges": [],
        "total_correct": 0,
        "name": target_name_found
    }
    
    for chat_id, game in active_games.items():
        for p in game.players:
            if p["id"] == target_id:
                p["coins"] = STARTING_COINS
                p["points"] = 0
                break
    
    save_player_data()
    save_game_data()
    
    bot.reply_to(
        message,
        f"🔐 **Secret Admin Action**\n\n"
        f"✅ Reset all stats for **{target_name_found}**!\n"
        f"🔄 They now have {STARTING_COINS} coins and 0 points.",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['allplayers'])
def list_all_players_secret(message):
    if not is_bot_owner(message):
        return
    
    # Show both user_database and player_data
    if not user_database and not player_data:
        bot.reply_to(message, "📋 No users found! Tell users to send `/start` to the bot.")
        return
    
    msg = "📋 **All Users**\n\n"
    
    # Show from user_database
    if user_database:
        msg += "👤 **Registered Users:**\n"
        for uid, data in user_database.items():
            name = data.get("first_name", "Unknown")
            username = data.get("username", "")
            display = f"{name} (@{username})" if username else name
            msg += f"• {display}\n"
            if uid in player_data:
                stats = player_data[uid]
                msg += f"  💰 {stats['coins']} coins | ⭐ {stats['points']} pts | 🏆 {stats['wins']} wins\n"
            else:
                msg += f"  💰 {STARTING_COINS} coins (not played yet)\n"
        msg += "\n"
    
    # Show from player_data (users not in user_database)
    for pid, stats in player_data.items():
        if pid not in user_database:
            name = stats.get("name", f"ID: {pid}")
            msg += f"• {name}\n"
            msg += f"  💰 {stats['coins']} coins | ⭐ {stats['points']} pts | 🏆 {stats['wins']} wins\n"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['addcoins'])
def add_coins(message):
    if not is_bot_owner(message):
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/addcoins @player amount`", parse_mode='Markdown')
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
    
    stats = get_player_stats(target["id"])
    stats["coins"] += amount
    target["coins"] += amount
    bot.reply_to(message, f"✅ Added {amount} coins to {target['name']}! New balance: {stats['coins']}")
    save_game_data()
    save_player_data()

@bot.message_handler(commands=['removecoins'])
def remove_coins(message):
    if not is_bot_owner(message):
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/removecoins @player amount`", parse_mode='Markdown')
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
    
    stats = get_player_stats(target["id"])
    if stats["coins"] < amount:
        bot.reply_to(message, f"❌ {target['name']} only has {stats['coins']} coins!")
        return
    
    stats["coins"] -= amount
    target["coins"] -= amount
    bot.reply_to(message, f"✅ Removed {amount} coins from {target['name']}! New balance: {stats['coins']}")
    save_game_data()
    save_player_data()

# ============================================================
# WEBHOOK
# ============================================================

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index():
    return '⚔️ Card Warfare Bot is running!', 200

if __name__ == '__main__':
    print("⚔️ CARD WARFARE BOT STARTED!")
    
    game_data = load_game_data()
    player_data = load_player_data()
    user_database = load_user_database()
    
    print(f"📂 Loaded {len(game_data.get('games', {}))} saved games")
    print(f"📂 Loaded {len(player_data)} player profiles")
    print(f"📂 Loaded {len(user_database)} registered users")
    
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL + '/' + BOT_TOKEN)
        print(f"✅ Webhook set to: {WEBHOOK_URL}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
