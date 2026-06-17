import os
import random
import time
import threading
import json
import re
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

# ===== INLINE KEYBOARD FUNCTIONS =====

def get_main_menu(chat_id, is_admin=False, game_exists=False, game_status=None):
    """Main menu with all commands as buttons - like UNO bot"""
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = []
    
    # Game creation/joining buttons
    if not game_exists or game_status == "waiting":
        buttons.append(InlineKeyboardButton("🎮 New Game", callback_data=f"new_{chat_id}"))
        buttons.append(InlineKeyboardButton("👋 Join Game", callback_data=f"join_{chat_id}"))
    elif game_status == "playing":
        buttons.append(InlineKeyboardButton("👋 Join Game", callback_data=f"join_{chat_id}"))
    
    # Mode selection
    buttons.append(InlineKeyboardButton("📊 Mode 4/6/8/10", callback_data=f"show_modes_{chat_id}"))
    
    # Start game (only for admin/creator)
    if is_admin and game_exists and game_status == "waiting":
        buttons.append(InlineKeyboardButton("🚀 Start Game", callback_data=f"start_{chat_id}"))
    
    # Info buttons
    buttons.append(InlineKeyboardButton("🏆 Score", callback_data=f"score_{chat_id}"))
    buttons.append(InlineKeyboardButton("💰 Coins", callback_data=f"coins_{chat_id}"))
    buttons.append(InlineKeyboardButton("🃏 My Card", callback_data=f"mycard_{chat_id}"))
    buttons.append(InlineKeyboardButton("📊 Status", callback_data=f"status_{chat_id}"))
    buttons.append(InlineKeyboardButton("👥 Players", callback_data=f"players_{chat_id}"))
    buttons.append(InlineKeyboardButton("🔄 History", callback_data=f"history_{chat_id}"))
    
    # Admin buttons
    if is_admin and game_exists:
        if game_status == "playing":
            buttons.append(InlineKeyboardButton("⏹️ Stop Game", callback_data=f"stop_{chat_id}"))
        buttons.append(InlineKeyboardButton("🔄 Reset Game", callback_data=f"reset_{chat_id}"))
    
    markup.add(*buttons)
    return markup

def get_player_buttons(game, seeker_id, chat_id):
    """Generate buttons for players who haven't been found yet"""
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
    buttons.append(InlineKeyboardButton("🏠 Menu", callback_data=f"menu_{chat_id}"))
    markup.add(*buttons)
    return markup

def get_mode_buttons(chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("👑 4 Players", callback_data=f"mode_{chat_id}_4"),
        InlineKeyboardButton("👑 6 Players", callback_data=f"mode_{chat_id}_6"),
        InlineKeyboardButton("👑 8 Players", callback_data=f"mode_{chat_id}_8"),
        InlineKeyboardButton("👑 10 Players", callback_data=f"mode_{chat_id}_10"),
        InlineKeyboardButton("🏠 Back to Menu", callback_data=f"menu_{chat_id}")
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
        self.start_message_id = None
        self.found_players = []
        
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
        
        seeker = self.get_current_seeker()
        target = self.get_target_role()
        
        return True, {
            "message": f"🎮 Game started! {len(self.players)} players, {self.mode}-Player Mode",
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
            
            if seeker["id"] not in self.found_players:
                self.found_players.append(seeker["id"])
            
            if bet_amount > 0:
                seeker["coins"] += bet_amount * 2
                bet_msg = f"💰 Won {bet_amount * 2} coins!"
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
                    "next_target": self.get_target_role(),
                    "next_points": self.get_points(),
                    "found_players": self.found_players.copy()
                }
        else:
            old_seeker_role = self.card_map[seeker_id]
            old_chosen_role = self.card_map[chosen_player_id]
            
            self.card_map[seeker_id] = old_chosen_role
            self.card_map[chosen_player_id] = old_seeker_role
            
            if bet_amount > 0:
                seeker["coins"] -= bet_amount
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
                    # Show menu after game over
                    show_menu(chat_id, call.from_user.id)
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
                # WRONG guess - new seeker gets buttons
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

@bot.callback_query_handler(func=lambda call: call.data.startswith('new_'))
def handle_new(call):
    chat_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    user_name = get_player_name(call.from_user)
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    if chat_id in active_games:
        game = active_games[chat_id]
        if game.status == "playing":
            bot.answer_callback_query(call.id, "❌ Game already in progress!", show_alert=True)
            return
    
    active_games[chat_id] = Game(mode=4, creator_id=user_id)
    save_game_data()
    
    # Add creator as first player
    game = active_games[chat_id]
    success, msg = game.add_player(user_id, user_name)
    
    bot.send_message(
        chat_id,
        f"🎮 **New Game Created!**\n\n"
        f"📌 Mode: 4 Players (default)\n"
        f"👑 Creator: {user_name}\n"
        f"👥 Players: 1/{game.mode}\n\n"
        f"Click buttons below to manage the game!",
        reply_markup=get_main_menu(chat_id, True, True, "waiting"),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "✅ New game created!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_'))
def handle_join(call):
    chat_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    user_name = get_player_name(call.from_user)
    
    if chat_id not in active_games:
        bot.answer_callback_query(call.id, "❌ No game! Click 'New Game' first!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if game.status == "playing":
        bot.answer_callback_query(call.id, "❌ Game already in progress!", show_alert=True)
        return
    
    success, msg = game.add_player(user_id, user_name)
    bot.answer_callback_query(call.id, msg, show_alert=True)
    
    if success:
        save_game_data()
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        is_admin = is_admin_or_creator(call.message, game)
        bot.send_message(
            chat_id,
            f"👥 **Players ({len(game.players)}/{game.mode})**\n\n" + 
            "\n".join([f"• {p['name']}" for p in game.players]) +
            f"\n\n👑 Creator: {game.creator_id}\n"
            f"📌 Click below to manage the game!",
            reply_markup=get_main_menu(chat_id, is_admin, True, game.status),
            parse_mode='Markdown'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('mode_'))
def handle_mode(call):
    try:
        parts = call.data.split('_')
        chat_id = int(parts[1])
        mode = int(parts[2])
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
            f"👑 Creator: {call.from_user.first_name}\n\n"
            f"Click 'Join Game' to join!",
            reply_markup=get_main_menu(chat_id, True, True, "waiting"),
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, f"✅ {mode}-Player mode set!")
        save_game_data()
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('show_modes_'))
def handle_show_modes(call):
    chat_id = int(call.data.split('_')[1])
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    bot.send_message(
        chat_id,
        "🎮 **Choose Game Mode:**",
        reply_markup=get_mode_buttons(chat_id),
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "📋 Choose mode")

@bot.callback_query_handler(func=lambda call: call.data.startswith('start_'))
def handle_start(call):
    chat_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    
    if chat_id not in active_games:
        bot.answer_callback_query(call.id, "❌ No game!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if game.status != "waiting":
        bot.answer_callback_query(call.id, "❌ Game already started!", show_alert=True)
        return
    
    if not is_admin_or_creator(call.message, game):
        bot.answer_callback_query(call.id, "❌ Only creator/admin can start!", show_alert=True)
        return
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
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
                f"🎮 **GAME STARTED!**\n\n"
                f"👑 **Seeker:** {result['seeker']['name']}\n"
                f"🎯 **Target:** {result['target']}\n"
                f"⭐ **Points:** {result['points']}\n"
                f"👥 **Active Players:** {active_count}\n\n"
                f"💡 Click a button to guess!",
                reply_markup=buttons,
                parse_mode='Markdown'
            )
            save_game_data()
            bot.answer_callback_query(call.id, "✅ Game started!")
        else:
            bot.send_message(chat_id, "❌ No active players to guess!")
            game.status = "ended"
            save_game_data()
    else:
        bot.send_message(chat_id, f"❌ {result}")
        bot.answer_callback_query(call.id, "❌ Failed", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def handle_cancel(call):
    chat_id = int(call.data.split('_')[1])
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    bot.answer_callback_query(call.id, "❌ Cancelled")

@bot.callback_query_handler(func=lambda call: call.data.startswith('stop_'))
def handle_stop(call):
    chat_id = int(call.data.split('_')[1])
    
    if chat_id not in active_games:
        bot.answer_callback_query(call.id, "❌ No active game!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if not is_admin_or_creator(call.message, game):
        bot.answer_callback_query(call.id, "❌ Only admin/creator!", show_alert=True)
        return
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    game.status = "ended"
    bot.send_message(chat_id, "⏹️ **Game stopped!**", parse_mode='Markdown')
    show_leaderboard_func(chat_id)
    save_game_data()
    bot.answer_callback_query(call.id, "✅ Game stopped!")
    show_menu(chat_id, call.from_user.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('reset_'))
def handle_reset(call):
    chat_id = int(call.data.split('_')[1])
    
    if chat_id not in active_games:
        bot.answer_callback_query(call.id, "❌ No active game!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if not is_admin_or_creator(call.message, game):
        bot.answer_callback_query(call.id, "❌ Only admin/creator!", show_alert=True)
        return
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    del active_games[chat_id]
    if chat_id in game_timers:
        del game_timers[chat_id]
    bot.send_message(chat_id, "🔄 **Game reset!** Click 'New Game' to start.", parse_mode='Markdown')
    save_game_data()
    bot.answer_callback_query(call.id, "✅ Game reset!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('menu_'))
def handle_menu(call):
    chat_id = int(call.data.split('_')[1])
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    show_menu(chat_id, call.from_user.id)
    bot.answer_callback_query(call.id, "🏠 Menu")

@bot.callback_query_handler(func=lambda call: call.data.startswith('score_'))
def handle_score(call):
    chat_id = int(call.data.split('_')[1])
    if chat_id in active_games:
        game = active_games[chat_id]
        sorted_players = game.get_leaderboard()
        msg = "🏆 **POINTS LEADERBOARD** 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, p in enumerate(sorted_players):
            medal = medals[i] if i < 3 else f"{i+1}."
            role = game.get_player_role(p["id"])
            status = "✅ Found" if p["id"] in game.found_players else "🔄 Active"
            msg += f"{medal} {p['name']} - **{p['points']}** pts ({role}) - {status}\n"
        bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "❌ No active game!")
    bot.answer_callback_query(call.id, "📊 Score")

@bot.callback_query_handler(func=lambda call: call.data.startswith('coins_'))
def handle_coins(call):
    chat_id = int(call.data.split('_')[1])
    if chat_id in active_games:
        game = active_games[chat_id]
        sorted_players = game.get_coin_leaderboard()
        msg = "💰 **COINS LEADERBOARD** 💰\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, p in enumerate(sorted_players):
            medal = medals[i] if i < 3 else f"{i+1}."
            role = game.get_player_role(p["id"])
            msg += f"{medal} {p['name']} - **{p['coins']}** coins ({role})\n"
        bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "❌ No active game!")
    bot.answer_callback_query(call.id, "💰 Coins")

@bot.callback_query_handler(func=lambda call: call.data.startswith('mycard_'))
def handle_mycard(call):
    chat_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    
    if chat_id in active_games:
        game = active_games[chat_id]
        role = game.get_player_role(user_id)
        player = game.get_player(user_id)
        if player:
            status = "✅ Found" if player["id"] in game.found_players else "🔄 Active"
            msg = f"🃏 **Your Role:** {role}\n💰 **Coins:** {player['coins']}\n⭐ **Points:** {player['points']}\n📌 **Status:** {status}"
            bot.send_message(chat_id, msg, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "❌ You're not in this game!")
    else:
        bot.send_message(chat_id, "❌ No active game!")
    bot.answer_callback_query(call.id, "🃏 Your Card")

@bot.callback_query_handler(func=lambda call: call.data.startswith('status_'))
def handle_status(call):
    chat_id = int(call.data.split('_')[1])
    if chat_id in active_games:
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
        
        bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "❌ No active game!")
    bot.answer_callback_query(call.id, "📊 Status")

@bot.callback_query_handler(func=lambda call: call.data.startswith('players_'))
def handle_players(call):
    chat_id = int(call.data.split('_')[1])
    if chat_id in active_games:
        game = active_games[chat_id]
        msg = "👥 **Players:**\n\n"
        for i, p in enumerate(game.players, 1):
            role = game.get_player_role(p["id"])
            status = "✅ Found" if p["id"] in game.found_players else "🔄 Active"
            msg += f"{i}. {p['name']} - {role} - {status}\n"
        bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "❌ No active game!")
    bot.answer_callback_query(call.id, "👥 Players")

@bot.callback_query_handler(func=lambda call: call.data.startswith('history_'))
def handle_history(call):
    chat_id = int(call.data.split('_')[1])
    if chat_id in active_games:
        game = active_games[chat_id]
        if not game.swap_history:
            bot.send_message(chat_id, "📋 No swaps yet!")
        else:
            msg = "🔄 **Swap History:**\n\n"
            for i, swap in enumerate(game.swap_history[-10:], 1):
                msg += f"{i}. {swap['seeker']} → {swap['chosen']}\n   {swap['swapped']}\n"
            bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "❌ No active game!")
    bot.answer_callback_query(call.id, "🔄 History")

# ===== SHOW MENU FUNCTION =====

def show_menu(chat_id, user_id):
    game = active_games.get(chat_id)
    is_admin = False
    game_exists = game is not None
    game_status = game.status if game_exists else None
    
    if game_exists:
        class FakeMessage:
            pass
        fake_msg = FakeMessage()
        fake_msg.from_user = type('obj', (object,), {'id': user_id})()
        fake_msg.chat = type('obj', (object,), {'id': chat_id})()
        is_admin = is_admin_or_creator(fake_msg, game)
    
    bot.send_message(
        chat_id,
        "🎮 **RAJA RANI GAME MENU**\n\n"
        "Click a button below to play!",
        reply_markup=get_main_menu(chat_id, is_admin, game_exists, game_status),
        parse_mode='Markdown'
    )

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

# ===== BOT COMMANDS =====

@bot.message_handler(commands=['start'])
def start_command(message):
    if message.chat.id > 0:
        help_text = """
🎮 **RAJA RANI BOT** 🎮

📌 **Commands:**
`/game` - Open game menu with buttons
`/menu` - Show game menu
`/bet X` - Bet 10-50 coins

⚡ **Rules:**
• Wrong guess = SWAP cards!
• Correct guess = Earn points!

*Enjoy!* 🎉
        """
        bot.reply_to(message, help_text, parse_mode='Markdown')
        return
    
    show_menu(message.chat.id, message.from_user.id)

@bot.message_handler(commands=['menu', 'game'])
def menu_command(message):
    if message.chat.id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    show_menu(message.chat.id, message.from_user.id)

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
        
        if player["coins"] < bet_amount:
            bot.reply_to(message, f"❌ You only have {player['coins']} coins!")
            return
        
        game.bets[player_id] = bet_amount
        bot.reply_to(message, f"💰 Bet placed: {bet_amount} coins!\n💡 Click a button to guess!")
        
    except ValueError:
        bot.reply_to(message, "❌ Enter a valid number!")

# ===== BOT OWNER & ADMIN COMMANDS =====

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
    show_menu(chat_id, message.from_user.id)

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
        bot.reply_to(message, "🔄 **Game reset!** Click 'New Game' to start.", parse_mode='Markdown')
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
    
    target["coins"] += amount
    bot.reply_to(message, f"✅ Added {amount} coins to {target['name']}! New balance: {target['coins']}")
    save_game_data()

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
    
    if target["coins"] < amount:
        bot.reply_to(message, f"❌ {target['name']} only has {target['coins']} coins!")
        return
    
    target["coins"] -= amount
    bot.reply_to(message, f"✅ Removed {amount} coins from {target['name']}! New balance: {target['coins']}")
    save_game_data()

@bot.message_handler(commands=['setcoins'])
def set_coins(message):
    if not is_bot_owner(message):
        return
    
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/setcoins @player amount`", parse_mode='Markdown')
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

# ===== WEBHOOK =====

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index():
    return '🤖 Raja Rani Bot is running!', 200

if __name__ == '__main__':
    print("🤖 RAJA RANI BOT STARTED!")
    data = load_game_data()
    print(f"📂 Loaded {len(data['games'])} saved games")
    
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    if WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL + '/' + BOT_TOKEN)
        print(f"✅ Webhook set to: {WEBHOOK_URL}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
