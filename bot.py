import os
import random
import time
import threading
import json
import re
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask, request
from config import BOT_TOKEN, BOT_OWNER_ID, TIMER_SECONDS, get_roles_for_players

# ===== INITIALIZATION =====
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ===== SET COMMAND SUGGESTIONS =====

def set_bot_commands():
    commands = [
        BotCommand("game", "⚔️ Create or join a game"),
        BotCommand("startgame", "🚀 Start game"),
        BotCommand("score", "🏆 View points leaderboard"),
        BotCommand("mycard", "🃏 View your role"),
        BotCommand("status", "📊 View game status"),
        BotCommand("players", "👥 View all players"),
        BotCommand("history", "🔄 View swap history"),
        BotCommand("kill", "💀 Kill/End current game"),
    ]
    bot.set_my_commands(commands)
    print("✅ Bot commands set!")

set_bot_commands()

# ===== GAME STORAGE =====
active_games = {}
game_timers = {}
game_history = {}

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

def strip_emoji(text):
    """Remove emojis and special characters from role name"""
    return re.sub(r'[^\w\s]', '', text).strip()

# ============================================================
# SAVE/LOAD GAME DATA
# ============================================================

def save_game_data():
    try:
        data = {"games": {}, "history": game_history}
        for chat_id, game in active_games.items():
            data["games"][str(chat_id)] = {
                "mode": game.mode,
                "players": game.players,
                "roles": game.roles,
                "points": game.points,
                "targets": game.targets,
                "current_level": game.current_level,
                "status": game.status,
                "card_map": game.card_map,
                "swap_history": game.swap_history,
                "creator_id": game.creator_id,
                "found_players": game.found_players,
                "menu_message_id": game.menu_message_id
            }
        with open("game_data.json", "w") as f:
            json.dump(data, f)
    except:
        pass

def load_game_data():
    try:
        with open("game_data.json", "r") as f:
            return json.load(f)
    except:
        return {"games": {}, "history": {}}

# ============================================================
# INLINE KEYBOARD FUNCTIONS
# ============================================================

def get_join_menu(game, chat_id):
    markup = InlineKeyboardMarkup(row_width=1)
    buttons = []
    
    if game.status == "waiting":
        buttons.append(InlineKeyboardButton("🎮 Join Game", callback_data=f"join_{chat_id}"))
    
    markup.add(*buttons)
    return markup

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
    
    markup.add(*buttons)
    return markup

# ============================================================
# GAME CLASS
# ============================================================

class Game:
    def __init__(self, creator_id=None):
        self.creator_id = creator_id
        self.players = []
        self.mode = 0
        self.roles = []
        self.points = []
        self.targets = []
        self.current_level = 0
        self.status = "waiting"
        self.card_map = {}
        self.swap_history = []
        self.start_time = None
        self.total_rounds = 0
        self.start_message_id = None
        self.found_players = []
        self.timer_active = False
        self.menu_message_id = None
        
    def set_mode_from_players(self):
        player_count = len(self.players)
        roles, points = get_roles_for_players(player_count)
        
        if roles is None:
            return False, f"❌ Need at least 4 players! (Currently {player_count})"
        
        self.roles = roles
        self.points = points
        self.targets = roles[1:]
        self.mode = player_count
        return True, f"✅ Mode set for {player_count} players!"
    
    def add_player(self, player_id, player_name):
        if len(self.players) >= 10:
            return False, "❌ Maximum 10 players reached!"
        if player_id in [p["id"] for p in self.players]:
            return False, "❌ You're already in the game!"
        
        if not check_dm_access(player_id):
            return False, f"❌ {player_name}, please start the bot in DM first!"
        
        self.players.append({
            "id": player_id, 
            "name": player_name, 
            "points": 0,
            "joined_at": datetime.now().isoformat()
        })
        
        return True, f"✅ {player_name} joined! ({len(self.players)} players)"
    
    def start_game(self):
        if len(self.players) < 4:
            return False, f"❌ Need at least 4 players! ({len(self.players)} currently)"
        
        success, msg = self.set_mode_from_players()
        if not success:
            return False, msg
        
        for p in self.players:
            if not check_dm_access(p["id"]):
                return False, f"❌ {p['name']} hasn't started the bot in DM!"
        
        shuffled_roles = self.roles.copy()
        random.shuffle(shuffled_roles)
        for i, player in enumerate(self.players):
            self.card_map[player["id"]] = shuffled_roles[i]
            player["points"] = 0
        
        self.status = "playing"
        self.start_time = time.time()
        self.current_level = 0
        self.total_rounds += 1
        self.found_players = []
        self.timer_active = True
        
        seeker = self.get_current_seeker()
        target = self.get_target_role()
        
        return True, {
            "message": f"⚔️ Game started! {len(self.players)} players",
            "seeker": seeker,
            "target": target,
            "points": self.get_points()
        }
    
    def get_current_seeker(self):
        if self.current_level >= len(self.roles) - 1:
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
        chosen_role_plain = strip_emoji(chosen_role_full)
        
        chosen_player = self.get_player(chosen_player_id)
        if not chosen_player:
            return False, "❌ Player not found!"
        
        if chosen_role_plain == target_role:
            points = self.get_points()
            seeker["points"] += points
            
            if seeker["id"] not in self.found_players:
                self.found_players.append(seeker["id"])
            
            self.current_level += 1
            
            if self.current_level >= len(self.targets):
                self.status = "ended"
                return True, {
                    "result": "correct",
                    "message": f"🎉🏆 {seeker['name']} found {target_role}! GAME OVER! Winner: {seeker['name']} with {seeker['points']} points!",
                    "points": points,
                    "game_over": True
                }
            else:
                next_seeker = self.get_current_seeker()
                return True, {
                    "result": "correct",
                    "message": f"✅ {seeker['name']} found {target_role}! +{points} points! 🎉",
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
            
            self.swap_history.append({
                "time": time.time(),
                "seeker": seeker["name"],
                "chosen": chosen_player["name"],
                "swapped": f"{old_seeker_role} ↔ {old_chosen_role}"
            })
            
            try:
                bot.send_message(
                    seeker["id"],
                    f"🔄 **Your card was swapped!**\n\n"
                    f"Your new role is: **{old_chosen_role}**\n"
                    f"🤫 Keep it secret!",
                    parse_mode='Markdown'
                )
            except:
                pass
            
            try:
                bot.send_message(
                    chosen_player["id"],
                    f"🔄 **Your card was swapped!**\n\n"
                    f"Your new role is: **{old_seeker_role}**\n"
                    f"🤫 Keep it secret!",
                    parse_mode='Markdown'
                )
            except:
                pass
            
            new_seeker = self.get_current_seeker()
            return True, {
                "result": "wrong",
                "message": f"❌ WRONG! {seeker['name']} pointed at {chosen_player['name']}!",
                "swap": f"🔄 Cards Swapped! (Roles kept secret)",
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
            return f"⏳ Waiting... ({len(self.players)} players)"
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

# ============================================================
# UPDATE MENU FUNCTION
# ============================================================

def update_game_menu(chat_id, game):
    """Update the game menu message with current player list"""
    if game.menu_message_id is None:
        return
    
    player_list = "\n".join([f"• {p['name']}" for p in game.players])
    
    text = (
        f"⚔️ **Game Menu**\n\n"
        f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
        f"📌 Minimum: 4 players to start\n"
        f"📌 Maximum: 10 players\n\n"
        f"📌 Click the button below to join!"
    )
    
    try:
        bot.edit_message_text(
            text,
            chat_id,
            game.menu_message_id,
            reply_markup=get_join_menu(game, chat_id),
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error updating menu: {e}")

def delete_game_menu(chat_id, game):
    """Delete the game menu message after game starts"""
    if game.menu_message_id is not None:
        try:
            bot.delete_message(chat_id, game.menu_message_id)
            game.menu_message_id = None
            save_game_data()
        except Exception as e:
            print(f"Error deleting menu: {e}")

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

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_'))
def handle_join(call):
    chat_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    user_name = get_player_name(call.from_user)
    
    if chat_id not in active_games:
        bot.answer_callback_query(call.id, "❌ No game found! Use /game first!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if game.status == "playing":
        bot.answer_callback_query(call.id, "❌ Game already started!", show_alert=True)
        return
    
    if len(game.players) >= 10:
        bot.answer_callback_query(call.id, "❌ Maximum 10 players reached!", show_alert=True)
        return
    
    success, msg = game.add_player(user_id, user_name)
    bot.answer_callback_query(call.id, msg, show_alert=True)
    
    if success:
        save_game_data()
        update_game_menu(chat_id, game)

@bot.callback_query_handler(func=lambda call: call.data.startswith('start_'))
def handle_start(call):
    chat_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    
    if chat_id not in active_games:
        bot.answer_callback_query(call.id, "❌ No game found!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if game.status != "waiting":
        bot.answer_callback_query(call.id, "❌ Game already started!", show_alert=True)
        return
    
    if not is_admin_or_creator(call.message, game):
        bot.answer_callback_query(call.id, "❌ Only creator/admin can start!", show_alert=True)
        return
    
    if len(game.players) < 4:
        bot.answer_callback_query(call.id, f"❌ Need {4 - len(game.players)} more players!", show_alert=True)
        return
    
    # DELETE THE MENU MESSAGE (Join button removed)
    delete_game_menu(chat_id, game)
    
    # Delete the callback message too
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
                    f"🃏 Your role: **{role}**\n🤫 Don't tell anyone!",
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
            bot.answer_callback_query(call.id, "✅ Game started!")
        else:
            bot.send_message(chat_id, "❌ No active players to guess!")
            game.status = "ended"
            save_game_data()
    else:
        bot.send_message(chat_id, f"❌ {result}")
        bot.answer_callback_query(call.id, "❌ Failed", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('score_'))
def handle_score(call):
    chat_id = int(call.data.split('_')[1])
    show_leaderboard_func(chat_id)
    bot.answer_callback_query(call.id, "📊 Score")

@bot.callback_query_handler(func=lambda call: call.data.startswith('mycard_'))
def handle_mycard(call):
    chat_id = int(call.data.split('_')[1])
    user_id = call.from_user.id
    
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
        bot.answer_callback_query(call.id, "❌ No game")
        return
    
    game = active_games[chat_id]
    role = game.get_player_role(user_id)
    player = game.get_player(user_id)
    
    if player:
        status = "✅ Found" if player["id"] in game.found_players else "🔄 Active"
        msg = f"🃏 **Your Role:** {role}\n⭐ **Points:** {player['points']}\n📌 **Status:** {status}"
        bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "❌ You're not in this game!")
    bot.answer_callback_query(call.id, "🃏 Your Card")

@bot.callback_query_handler(func=lambda call: call.data.startswith('status_'))
def handle_status(call):
    chat_id = int(call.data.split('_')[1])
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
        bot.answer_callback_query(call.id, "❌ No game")
        return
    
    game = active_games[chat_id]
    status = game.get_status()
    
    msg = f"📊 **GAME STATUS**\n\n{status}\n\n"
    msg += f"👥 **Players:** {len(game.players)}\n"
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
    bot.answer_callback_query(call.id, "📊 Status")

@bot.callback_query_handler(func=lambda call: call.data.startswith('players_'))
def handle_players(call):
    chat_id = int(call.data.split('_')[1])
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
        bot.answer_callback_query(call.id, "❌ No game")
        return
    
    game = active_games[chat_id]
    msg = "👥 **Players:**\n\n"
    for i, p in enumerate(game.players, 1):
        role = game.get_player_role(p["id"])
        status = "✅ Found" if p["id"] in game.found_players else "🔄 Active"
        msg += f"{i}. {p['name']} - {role} - {status}\n"
    
    bot.send_message(chat_id, msg, parse_mode='Markdown')
    bot.answer_callback_query(call.id, "👥 Players")

@bot.callback_query_handler(func=lambda call: call.data.startswith('history_'))
def handle_history(call):
    chat_id = int(call.data.split('_')[1])
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
        bot.answer_callback_query(call.id, "❌ No game")
        return
    
    game = active_games[chat_id]
    if not game.swap_history:
        bot.send_message(chat_id, "📋 No swaps yet!")
    else:
        msg = "🔄 **Swap History:**\n\n"
        for i, swap in enumerate(game.swap_history[-10:], 1):
            msg += f"{i}. {swap['seeker']} → {swap['chosen']}\n"
        bot.send_message(chat_id, msg, parse_mode='Markdown')
    bot.answer_callback_query(call.id, "🔄 History")

@bot.callback_query_handler(func=lambda call: call.data.startswith('kill_'))
def handle_kill(call):
    chat_id = int(call.data.split('_')[1])
    
    if chat_id not in active_games:
        bot.answer_callback_query(call.id, "❌ No active game!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if not is_admin_or_creator(call.message, game):
        bot.answer_callback_query(call.id, "❌ Only creator/admin can kill!", show_alert=True)
        return
    
    if game.status != "playing":
        bot.answer_callback_query(call.id, "❌ Game is not active!", show_alert=True)
        return
    
    game.status = "ended"
    game.timer_active = False
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    bot.send_message(
        chat_id,
        f"💀 **GAME KILLED!**\n\n"
        f"**{call.from_user.first_name}** ended the game!\n"
        f"👥 Final players: {len(game.players)}\n"
        f"📊 Final results:",
        parse_mode='Markdown'
    )
    
    show_leaderboard_func(chat_id)
    save_game_data()
    bot.answer_callback_query(call.id, "💀 Game killed!")

@bot.callback_query_handler(func=lambda call: call.data == 'noop')
def handle_noop(call):
    bot.answer_callback_query(call.id, "⏳ Need 4 players to start!", show_alert=True)

# ============================================================
# SHOW LEADERBOARD FUNCTION
# ============================================================

def show_leaderboard_func(chat_id):
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
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
    bot.send_message(chat_id, msg, parse_mode='Markdown')

# ============================================================
# BOT COMMANDS
# ============================================================

@bot.message_handler(commands=['start'])
def start_command(message):
    try:
        delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    help_text = """
⚔️ **CARD WARFARE BOT** ⚔️

📌 **Commands:**
`/game` - Create or join a game
`/score` - Points leaderboard
`/mycard` - Your role & stats
`/status` - Game status
`/players` - List players
`/history` - Swap history

⚡ **Rules:**
• 4-10 players can join
• Wrong guess = SWAP cards!
• Correct guess = Earn points!
• Found players are removed from next rounds

*Enjoy!* 🎉
    """
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['game'])
def game_command(message):
    chat_id = message.chat.id
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    user_id = message.from_user.id
    user_name = get_player_name(message.from_user)
    
    if chat_id not in active_games:
        game = Game(creator_id=user_id)
        active_games[chat_id] = game
        game.add_player(user_id, user_name)
        save_game_data()
        
        player_list = "\n".join([f"• {p['name']}" for p in game.players])
        
        sent_msg = bot.send_message(
            chat_id,
            f"⚔️ **Game Menu**\n\n"
            f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
            f"📌 Minimum: 4 players to start\n"
            f"📌 Maximum: 10 players\n\n"
            f"📌 Click the button below to join!",
            reply_markup=get_join_menu(game, chat_id),
            parse_mode='Markdown'
        )
        
        game.menu_message_id = sent_msg.message_id
        save_game_data()
        
    else:
        game = active_games[chat_id]
        if game.status == "playing":
            bot.send_message(chat_id, "❌ Game already in progress!")
            return
        
        player_list = "\n".join([f"• {p['name']}" for p in game.players])
        
        sent_msg = bot.send_message(
            chat_id,
            f"⚔️ **Game Menu**\n\n"
            f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
            f"📌 Minimum: 4 players to start\n"
            f"📌 Maximum: 10 players\n\n"
            f"📌 Click the button below to join!",
            reply_markup=get_join_menu(game, chat_id),
            parse_mode='Markdown'
        )
        
        game.menu_message_id = sent_msg.message_id
        save_game_data()

@bot.message_handler(commands=['startgame'])
def startgame_command(message):
    chat_id = message.chat.id
    
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    if chat_id > 0:
        bot.send_message(chat_id, "❌ This command only works in groups!")
        return
    
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No game found! Use /game first!")
        return
    
    game = active_games[chat_id]
    
    if game.status != "waiting":
        bot.send_message(chat_id, "❌ Game already started or ended!")
        return
    
    if not is_admin_or_creator(message, game):
        bot.send_message(chat_id, "❌ Only the game creator or group admin can start the game!")
        return
    
    if len(game.players) < 4:
        bot.send_message(chat_id, f"❌ Need {4 - len(game.players)} more players!")
        return
    
    # DELETE THE MENU MESSAGE (Join button removed)
    delete_game_menu(chat_id, game)
    
    success, result = game.start_game()
    
    if success:
        for player in game.players:
            role = game.get_player_role(player["id"])
            try:
                bot.send_message(
                    player["id"], 
                    f"🃏 Your role: **{role}**\n🤫 Don't tell anyone!",
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

@bot.message_handler(commands=['score'])
def show_leaderboard(message):
    chat_id = message.chat.id
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    show_leaderboard_func(chat_id)

@bot.message_handler(commands=['mycard'])
def show_my_card(message):
    chat_id = message.chat.id
    player_id = message.from_user.id
    
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    role = game.get_player_role(player_id)
    player = game.get_player(player_id)
    
    if player:
        status = "✅ Found" if player["id"] in game.found_players else "🔄 Active"
        msg = f"🃏 **Your Role:** {role}\n⭐ **Points:** {player['points']}\n📌 **Status:** {status}"
        bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "❌ You're not in this game!")

@bot.message_handler(commands=['status'])
def show_status(message):
    chat_id = message.chat.id
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    status = game.get_status()
    
    msg = f"📊 **GAME STATUS**\n\n{status}\n\n"
    msg += f"👥 **Players:** {len(game.players)}\n"
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

@bot.message_handler(commands=['players'])
def show_players(message):
    chat_id = message.chat.id
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    msg = "👥 **Players:**\n\n"
    for i, p in enumerate(game.players, 1):
        role = game.get_player_role(p["id"])
        status = "✅ Found" if p["id"] in game.found_players else "🔄 Active"
        msg += f"{i}. {p['name']} - {role} - {status}\n"
    
    bot.send_message(chat_id, msg, parse_mode='Markdown')

@bot.message_handler(commands=['history'])
def show_history(message):
    chat_id = message.chat.id
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game!")
        return
    
    game = active_games[chat_id]
    if not game.swap_history:
        bot.send_message(chat_id, "📋 No swaps yet!")
        return
    
    msg = "🔄 **Swap History:**\n\n"
    for i, swap in enumerate(game.swap_history[-10:], 1):
        msg += f"{i}. {swap['seeker']} → {swap['chosen']}\n"
    bot.send_message(chat_id, msg, parse_mode='Markdown')

# ============================================================
# ADMIN COMMANDS
# ============================================================

@bot.message_handler(commands=['kill'])
def kill_game(message):
    chat_id = message.chat.id
    
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    if chat_id > 0:
        bot.send_message(chat_id, "❌ This command only works in groups!")
        return
    
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No active game to kill!")
        return
    
    game = active_games[chat_id]
    
    if not is_admin_or_creator(message, game):
        bot.send_message(chat_id, "❌ Only the game creator or group admin can kill the game!")
        return
    
    if game.status != "playing":
        bot.send_message(chat_id, "❌ Game is not active!")
        return
    
    game.status = "ended"
    game.timer_active = False
    
    bot.send_message(
        chat_id,
        f"💀 **GAME KILLED!**\n\n"
        f"**{message.from_user.first_name}** ended the game!\n"
        f"👥 Final players: {len(game.players)}\n"
        f"📊 Final results:",
        parse_mode='Markdown'
    )
    
    show_leaderboard_func(chat_id)
    save_game_data()
    
    if chat_id in game_timers:
        try:
            del game_timers[chat_id]
        except:
            pass

@bot.message_handler(commands=['reset'])
def reset_game(message):
    chat_id = message.chat.id
    
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    if chat_id > 0:
        bot.send_message(chat_id, "❌ This command only works in groups!")
        return
    
    if not is_admin_or_creator(message, active_games.get(chat_id)):
        bot.send_message(chat_id, "❌ Only admin/creator can reset!")
        return
    
    if chat_id in active_games:
        del active_games[chat_id]
        if chat_id in game_timers:
            del game_timers[chat_id]
        bot.send_message(chat_id, "🔄 **Game reset!** Use `/game` to start new.", parse_mode='Markdown')
        save_game_data()
    else:
        bot.send_message(chat_id, "❌ No game to reset!")

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
    print(f"📂 Loaded {len(game_data.get('games', {}))} saved games")
    
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    if WEBHOOK_URL:
        try:
            bot.remove_webhook()
            bot.set_webhook(url=WEBHOOK_URL + '/' + BOT_TOKEN)
            print(f"✅ Webhook set to: {WEBHOOK_URL}")
        except Exception as e:
            print(f"⚠️ Webhook error: {e}")
            print("ℹ️ Bot will still work with polling")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
