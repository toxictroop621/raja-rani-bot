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
        BotCommand("game", "⚔️ Classic Mode - Find your target"),
        BotCommand("collect", "🃏 Collection Mode - Collect 4 identical cards"),
        BotCommand("startgame", "🚀 Start game"),
        BotCommand("score", "🏆 View points leaderboard"),
        BotCommand("mycard", "🃏 View your role/cards"),
        BotCommand("status", "📊 View game status"),
        BotCommand("players", "👥 View all players"),
        BotCommand("history", "🔄 View swap history"),
        BotCommand("kill", "💀 Kill/End current game"),
        BotCommand("reset", "🔄 Reset game"),
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
    return re.sub(r'[^\w\s]', '', text).strip()

def get_role_name(role_with_emoji):
    return strip_emoji(role_with_emoji)

def get_card_emoji(card_type):
    emojis = {
        "King": "👑", "Queen": "👸", "Minister": "🧙", "Commander": "⚔️",
        "Detective": "🕵️", "Spy": "🥷", "Guard": "🛡️", "Police": "👮", "Chor": "🕵️",
        "Police Chief": "👮"
    }
    return emojis.get(card_type, "🃏")

# ============================================================
# SAVE/LOAD GAME DATA
# ============================================================

def save_game_data():
    try:
        data = {"games": {}, "history": game_history}
        for chat_id, game in active_games.items():
            if isinstance(game, ClassicGame):
                data["games"][str(chat_id)] = {
                    "type": "classic",
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
            elif isinstance(game, CollectionGame):
                data["games"][str(chat_id)] = {
                    "type": "collection",
                    "players": game.players,
                    "player_cards": game.player_cards,
                    "turn_index": game.turn_index,
                    "status": game.status,
                    "winners": game.winners,
                    "card_types": game.card_types,
                    "starting_player": game.starting_player,
                    "creator_id": game.creator_id
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
# CLASSIC MODE
# ============================================================

class ClassicGame:
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
        self.targets = [get_role_name(r) for r in roles[1:]]
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
        chosen_role_plain = get_role_name(chosen_role_full)
        
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
# COLLECTION MODE
# ============================================================

class CollectionGame:
    def __init__(self, creator_id=None):
        self.creator_id = creator_id
        self.players = []
        self.player_cards = {}
        self.turn_index = 0
        self.status = "waiting"
        self.winners = []
        self.card_types = []
        self.starting_player = None
        self.total_cards_per_type = 4
        self.cards_per_player = 4
        
    def get_card_types(self, player_count):
        all_types = ["King", "Queen", "Minister", "Commander", "Detective", "Spy", "Guard", "Police", "Chor"]
        if player_count == 4:
            return ["King", "Queen", "Police", "Chor"]
        elif player_count == 5:
            return ["King", "Queen", "Minister", "Police", "Chor"]
        else:
            return all_types[:player_count]
    
    def get_max_winners(self):
        count = len(self.players)
        if count == 4:
            return 1
        elif count == 5:
            return 2
        else:
            return 3
    
    def add_player(self, player_id, player_name):
        if len(self.players) >= 10:
            return False, "❌ Maximum 10 players reached!"
        if player_id in [p["id"] for p in self.players]:
            return False, "❌ You're already in the game!"
        self.players.append({"id": player_id, "name": player_name})
        return True, f"✅ {player_name} joined! ({len(self.players)} players)"
    
    def deal_cards(self):
        self.card_types = self.get_card_types(len(self.players))
        deck = []
        for ct in self.card_types:
            deck.extend([ct] * self.total_cards_per_type)
        random.shuffle(deck)
        
        idx = 0
        for p in self.players:
            self.player_cards[p["id"]] = deck[idx:idx + self.cards_per_player]
            idx += self.cards_per_player
    
    def start_game(self):
        if len(self.players) < 4:
            return False, f"❌ Need at least 4 players! ({len(self.players)} currently)"
        
        self.deal_cards()
        self.status = "playing"
        self.winners = []
        self.starting_player = random.randint(0, len(self.players) - 1)
        self.turn_index = self.starting_player
        
        return True, {
            "players": self.players,
            "starting_player": self.players[self.starting_player],
            "card_types": self.card_types
        }
    
    def get_current_player(self):
        if self.turn_index < len(self.players):
            return self.players[self.turn_index]
        return None
    
    def get_next_player(self):
        if not self.players:
            return None
        next_idx = (self.turn_index + 1) % len(self.players)
        return self.players[next_idx]
    
    def get_player_cards(self, player_id):
        return self.player_cards.get(player_id, [])
    
    def pass_card(self, player_id, card_type):
        player = self.get_player(player_id)
        if not player:
            return False, "❌ Player not found!"
        
        if card_type not in self.player_cards[player_id]:
            return False, "❌ You don't have that card!"
        
        self.player_cards[player_id].remove(card_type)
        
        receiver = self.get_next_player()
        if receiver:
            self.player_cards[receiver["id"]].append(card_type)
        
        self.turn_index = (self.turn_index + 1) % len(self.players)
        
        return True, {"sender": player, "receiver": receiver, "card": card_type}
    
    def check_winner(self, player_id):
        cards = self.player_cards.get(player_id, [])
        for ct in self.card_types:
            if cards.count(ct) >= 4:
                return True, ct
        return False, None
    
    def get_player(self, player_id):
        for p in self.players:
            if p["id"] == player_id:
                return p
        return None

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

def get_collection_card_buttons(game, player_id):
    """Get card buttons for collection mode - ONLY current player sees these"""
    cards = game.get_player_cards(player_id)
    if not cards:
        return None
    
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for c in cards:
        emoji = get_card_emoji(c)
        buttons.append(InlineKeyboardButton(f"{emoji} {c}", callback_data=f"pass_{c}_{player_id}"))
    markup.add(*buttons)
    return markup

# ============================================================
# UPDATE MENU FUNCTIONS
# ============================================================

def update_game_menu(chat_id, game):
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
    if game.menu_message_id is not None:
        try:
            bot.delete_message(chat_id, game.menu_message_id)
            game.menu_message_id = None
            save_game_data()
        except Exception as e:
            print(f"Error deleting menu: {e}")

# ============================================================
# COLLECTION MODE - GROUP ONLY (Like UNO/Rummy)
# ============================================================

def show_collection_turn(chat_id, game):
    """Show turn - ONLY current player sees their cards"""
    player = game.get_current_player()
    if not player:
        return
    
    next_p = game.get_next_player()
    if not next_p:
        return
    
    # Public announcement - everyone sees (NO CARDS)
    bot.send_message(
        chat_id,
        f"🔄 @{player['name']}'s turn! Pass a card to @{next_p['name']}! 🤫",
        parse_mode='Markdown'
    )
    
    # Show card buttons ONLY to the current player
    cards = game.get_player_cards(player["id"])
    if not cards:
        bot.send_message(chat_id, f"❌ {player['name']} has no cards left!")
        return
    
    markup = get_collection_card_buttons(game, player["id"])
    if markup:
        # Send card selection message - only the player sees this
        bot.send_message(
            chat_id,
            f"@{player['name']}, choose which card to pass 👇",
            reply_markup=markup,
            parse_mode='Markdown'
        )
    else:
        bot.send_message(chat_id, f"❌ {player['name']} has no cards left!")

def show_collection_winners(chat_id, game):
    msg = "🏆 **GAME OVER!** 🏆\n\n"
    ranks = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(game.winners):
        rank = ranks[i] if i < 3 else f"{i+1}."
        msg += f"{rank} {p['name']}\n"
    bot.send_message(chat_id, msg, parse_mode='Markdown')

# ============================================================
# CALLBACK HANDLERS - Classic Mode
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
        
        if not isinstance(game, ClassicGame):
            bot.answer_callback_query(call.id, "❌ Not a Classic game!", show_alert=True)
            return
        
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
        bot.answer_callback_query(call.id, "❌ No game found! Use /game or /collect first!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    if game.status == "playing":
        bot.answer_callback_query(call.id, "❌ Game already started!", show_alert=True)
        return
    
    if len(game.players) >= 10:
        bot.answer_callback_query(call.id, "❌ Maximum 10 players reached!", show_alert=True)
        return
    
    if isinstance(game, ClassicGame):
        success, msg = game.add_player(user_id, user_name)
        bot.answer_callback_query(call.id, msg, show_alert=True)
        if success:
            save_game_data()
            update_game_menu(chat_id, game)
    elif isinstance(game, CollectionGame):
        success, msg = game.add_player(user_id, user_name)
        bot.answer_callback_query(call.id, msg, show_alert=True)
        if success:
            save_game_data()
            player_list = "\n".join([f"• {p['name']}" for p in game.players])
            bot.send_message(
                chat_id,
                f"🃏 **Collection Mode - Players**\n\n"
                f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
                f"📌 Minimum: 4 players to start\n"
                f"📌 Maximum: 10 players\n\n"
                f"🚀 Use `/startgame` to begin!",
                parse_mode='Markdown'
            )

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
    
    delete_game_menu(chat_id, game)
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    if isinstance(game, ClassicGame):
        success, result = game.start_game()
        if not success:
            bot.send_message(chat_id, f"❌ {result}")
            bot.answer_callback_query(call.id, "❌ Failed", show_alert=True)
            return
        
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
    
    elif isinstance(game, CollectionGame):
        success, result = game.start_game()
        if not success:
            bot.send_message(chat_id, f"❌ {result}")
            bot.answer_callback_query(call.id, "❌ Failed", show_alert=True)
            return
        
        start = result["starting_player"]
        next_p = game.get_next_player()
        
        bot.send_message(
            chat_id,
            f"🃏 **COLLECTION MODE STARTED!**\n\n"
            f"🎲 Starting player: **{start['name']}**\n"
            f"📌 Collect 4 identical cards to win!\n\n"
            f"🔄 **@{start['name']}'s turn!** Pass a card to @{next_p['name']}!",
            parse_mode='Markdown'
        )
        
        show_collection_turn(chat_id, game)
        save_game_data()
        bot.answer_callback_query(call.id, "✅ Game started!")

# ============================================================
# CALLBACK HANDLERS - Collection Mode
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('pass_'))
def handle_collection_pass(call):
    try:
        _, card, player_id = call.data.split('_')
        player_id = int(player_id)
        chat_id = call.message.chat.id
        
        if call.from_user.id != player_id:
            bot.answer_callback_query(call.id, "❌ It's not your turn!", show_alert=True)
            return
        
        if chat_id not in active_games:
            bot.answer_callback_query(call.id, "❌ No active game!", show_alert=True)
            return
        
        game = active_games[chat_id]
        
        if not isinstance(game, CollectionGame):
            bot.answer_callback_query(call.id, "❌ Not a Collection game!", show_alert=True)
            return
        
        if game.status != "playing":
            bot.answer_callback_query(call.id, "❌ Game is not active!", show_alert=True)
            return
        
        current = game.get_current_player()
        if not current or current["id"] != player_id:
            bot.answer_callback_query(call.id, "❌ It's not your turn!", show_alert=True)
            return
        
        success, result = game.pass_card(player_id, card)
        if not success:
            bot.answer_callback_query(call.id, f"❌ {result}", show_alert=True)
            return
        
        # Delete the pass message (so others don't see the buttons)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        # Public announcement (NO CARD DETAILS)
        sender = result["sender"]
        receiver = result["receiver"]
        bot.send_message(
            chat_id,
            f"🔄 @{sender['name']} passed a card to @{receiver['name']}! 🤫",
            parse_mode='Markdown'
        )
        
        # Check if receiver won
        has_won, card_type = game.check_winner(receiver["id"])
        if has_won:
            game.winners.append(receiver)
            max_winners = game.get_max_winners()
            
            emoji = get_card_emoji(card_type)
            bot.send_message(
                chat_id,
                f"🎉🎉🎉 **@{receiver['name']} WINS!** 🎉🎉🎉\n\n"
                f"{receiver['name']} collected 4 {emoji} {card_type} cards!\n"
                f"🏆 Rank: #{len(game.winners)}",
                parse_mode='Markdown'
            )
            
            if len(game.winners) >= max_winners:
                game.status = "ended"
                show_collection_winners(chat_id, game)
                save_game_data()
                bot.answer_callback_query(call.id, "🏆 Game Over!")
                return
        
        # Show next turn
        show_collection_turn(chat_id, game)
        save_game_data()
        bot.answer_callback_query(call.id, "✅ Card passed!")
        
    except Exception as e:
        print(f"Error: {e}")
        bot.answer_callback_query(call.id, "❌ Error!", show_alert=True)

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
    
    if isinstance(game, ClassicGame):
        role = game.get_player_role(user_id)
        player = game.get_player(user_id)
        if player:
            status = "✅ Found" if player["id"] in game.found_players else "🔄 Active"
            msg = f"🃏 **Your Role:** {role}\n⭐ **Points:** {player['points']}\n📌 **Status:** {status}"
            bot.send_message(chat_id, msg, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "❌ You're not in this game!")
    elif isinstance(game, CollectionGame):
        cards = game.get_player_cards(user_id)
        if cards:
            card_list = "\n".join([f"• {get_card_emoji(c)} {c}" for c in cards])
            msg = f"🃏 **Your Cards ({len(cards)}):**\n\n{card_list}"
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
    
    if isinstance(game, ClassicGame):
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
    elif isinstance(game, CollectionGame):
        current = game.get_current_player()
        next_p = game.get_next_player()
        msg = f"🃏 **COLLECTION MODE STATUS**\n\n"
        msg += f"👥 **Players:** {len(game.players)}\n"
        msg += f"🏆 **Winners:** {len(game.winners)}/{game.get_max_winners()}\n"
        if current:
            msg += f"👑 **Current Turn:** {current['name']}\n"
        if next_p:
            msg += f"➡️ **Next Player:** {next_p['name']}\n"
        
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
        if isinstance(game, ClassicGame):
            role = game.get_player_role(p["id"])
            status = "✅ Found" if p["id"] in game.found_players else "🔄 Active"
            msg += f"{i}. {p['name']} - {role} - {status}\n"
        else:
            cards = game.get_player_cards(p["id"])
            card_count = len(cards) if cards else 0
            msg += f"{i}. {p['name']} - {card_count} cards\n"
    
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
    
    if isinstance(game, ClassicGame):
        if not game.swap_history:
            bot.send_message(chat_id, "📋 No swaps yet!")
        else:
            msg = "🔄 **Swap History:**\n\n"
            for i, swap in enumerate(game.swap_history[-10:], 1):
                msg += f"{i}. {swap['seeker']} → {swap['chosen']}\n"
            bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "📋 History only available in Classic Mode!")
    
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
    if isinstance(game, ClassicGame):
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
    
    if isinstance(game, ClassicGame):
        show_leaderboard_func(chat_id)
    elif isinstance(game, CollectionGame):
        if game.winners:
            show_collection_winners(chat_id, game)
        else:
            bot.send_message(chat_id, "No winners yet!")
    
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
    
    if not isinstance(game, ClassicGame):
        bot.send_message(chat_id, "❌ Leaderboard only available in Classic Mode!")
        return
    
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

**Classic Mode:**
`/game` - Start Classic Mode (Find target → Swap roles)
`/point @player` - Guess who has the target role
`/score` - View points leaderboard
`/mycard` - View your role

**Collection Mode:**
`/collect` - Start Collection Mode (Collect 4 identical cards)

**General:**
`/startgame` - Start the game (Creator/Admin only)
`/status` - View game status
`/players` - View all players
`/history` - View swap history (Classic Mode)
`/kill` - Kill/End current game
`/reset` - Reset game

⚡ **Classic Mode Rules:**
• Wrong guess = SWAP cards!
• Correct guess = Earn points!
• Found players are removed from next rounds

🃏 **Collection Mode Rules:**
• Collect 4 identical cards to win!
• Pass cards to other players
• First to collect 4 cards wins!
• Cards are ONLY visible to the player!

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
    
    # Check if collection game is active
    if chat_id in active_games and isinstance(active_games[chat_id], CollectionGame) and active_games[chat_id].status == "playing":
        bot.send_message(chat_id, "❌ A Collection game is already in progress! Use /kill to end it.")
        return
    
    # Check if classic game exists
    if chat_id in active_games and isinstance(active_games[chat_id], ClassicGame):
        game = active_games[chat_id]
        if game.status == "playing":
            bot.send_message(chat_id, "❌ Game already in progress!")
            return
        
        player_list = "\n".join([f"• {p['name']}" for p in game.players]) if game.players else "No players yet"
        bot.send_message(
            chat_id,
            f"⚔️ **Classic Mode - Game Menu**\n\n"
            f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
            f"📌 Minimum: 4 players to start\n"
            f"📌 Maximum: 10 players\n\n"
            f"👋 Use `/join` to join!\n"
            f"🚀 Use `/startgame` to begin!",
            parse_mode='Markdown'
        )
        return
    
    # Create new classic game
    game = ClassicGame(creator_id=user_id)
    active_games[chat_id] = game
    game.add_player(user_id, user_name)
    save_game_data()
    
    player_list = "\n".join([f"• {p['name']}" for p in game.players])
    
    sent_msg = bot.send_message(
        chat_id,
        f"⚔️ **Classic Mode created!**\n\n"
        f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
        f"📌 Minimum: 4 players to start\n"
        f"📌 Maximum: 10 players\n\n"
        f"📌 Click the button below to join!\n"
        f"🚀 Use `/startgame` to begin!",
        reply_markup=get_join_menu(game, chat_id),
        parse_mode='Markdown'
    )
    
    game.menu_message_id = sent_msg.message_id
    save_game_data()

@bot.message_handler(commands=['collect'])
def collect_command(message):
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
    
    # Check if classic game is active
    if chat_id in active_games and isinstance(active_games[chat_id], ClassicGame) and active_games[chat_id].status == "playing":
        bot.send_message(chat_id, "❌ A Classic game is already in progress! Use /kill to end it.")
        return
    
    # Check if collection game exists
    if chat_id in active_games and isinstance(active_games[chat_id], CollectionGame):
        game = active_games[chat_id]
        if game.status == "playing":
            bot.send_message(chat_id, "❌ Game already in progress!")
            return
        
        player_list = "\n".join([f"• {p['name']}" for p in game.players]) if game.players else "No players yet"
        bot.send_message(
            chat_id,
            f"🃏 **Collection Mode - Game Menu**\n\n"
            f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
            f"📌 Minimum: 4 players to start\n"
            f"📌 Maximum: 10 players\n\n"
            f"👋 Use `/join` to join!\n"
            f"🚀 Use `/startgame` to begin!",
            parse_mode='Markdown'
        )
        return
    
    # Create new collection game
    game = CollectionGame(creator_id=user_id)
    active_games[chat_id] = game
    game.add_player(user_id, user_name)
    save_game_data()
    
    player_list = "\n".join([f"• {p['name']}" for p in game.players])
    
    bot.send_message(
        chat_id,
        f"🃏 **Collection Mode created!**\n\n"
        f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
        f"📌 Minimum: 4 players to start\n"
        f"📌 Maximum: 10 players\n\n"
        f"👋 Use `/join` to join!\n"
        f"🚀 Use `/startgame` to begin!",
        parse_mode='Markdown'
    )
    save_game_data()

@bot.message_handler(commands=['join'])
def join_command(message):
    chat_id = message.chat.id
    
    if chat_id > 0:
        bot.reply_to(message, "❌ This command only works in groups!")
        return
    
    try:
        delete_message(chat_id, message.message_id)
    except:
        pass
    
    if chat_id not in active_games:
        bot.send_message(chat_id, "❌ No game! Use `/game` or `/collect` first.", parse_mode='Markdown')
        return
    
    game = active_games[chat_id]
    user_id = message.from_user.id
    user_name = get_player_name(message.from_user)
    
    if game.status == "playing":
        bot.send_message(chat_id, "❌ Game already started!")
        return
    
    if len(game.players) >= 10:
        bot.send_message(chat_id, "❌ Maximum 10 players reached!")
        return
    
    success, msg = game.add_player(user_id, user_name)
    bot.send_message(chat_id, msg)
    
    if success:
        save_game_data()
        player_list = "\n".join([f"• {p['name']}" for p in game.players])
        mode_name = "⚔️ Classic Mode" if isinstance(game, ClassicGame) else "🃏 Collection Mode"
        bot.send_message(
            chat_id,
            f"{mode_name}\n\n"
            f"👥 Players ({len(game.players)}):\n{player_list}\n\n"
            f"📌 Minimum: 4 players to start\n"
            f"📌 Maximum: 10 players\n\n"
            f"🚀 Use `/startgame` to begin!",
            parse_mode='Markdown'
        )

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
        bot.send_message(chat_id, "❌ No game found! Use `/game` or `/collect` first!", parse_mode='Markdown')
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
    
    if isinstance(game, ClassicGame):
        delete_game_menu(chat_id, game)
        
        success, result = game.start_game()
        if not success:
            bot.send_message(chat_id, f"❌ {result}")
            return
        
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
    
    elif isinstance(game, CollectionGame):
        success, result = game.start_game()
        if not success:
            bot.send_message(chat_id, f"❌ {result}")
            return
        
        start = result["starting_player"]
        next_p = game.get_next_player()
        
        bot.send_message(
            chat_id,
            f"🃏 **COLLECTION MODE STARTED!**\n\n"
            f"🎲 Starting player: **{start['name']}**\n"
            f"📌 Collect 4 identical cards to win!\n\n"
            f"🔄 **@{start['name']}'s turn!** Pass a card to @{next_p['name']}!",
            parse_mode='Markdown'
        )
        
        show_collection_turn(chat_id, game)
        save_game_data()

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
    
    if isinstance(game, ClassicGame):
        role = game.get_player_role(player_id)
        player = game.get_player(player_id)
        if player:
            status = "✅ Found" if player["id"] in game.found_players else "🔄 Active"
            msg = f"🃏 **Your Role:** {role}\n⭐ **Points:** {player['points']}\n📌 **Status:** {status}"
            bot.send_message(chat_id, msg, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "❌ You're not in this game!")
    
    elif isinstance(game, CollectionGame):
        cards = game.get_player_cards(player_id)
        if cards:
            card_list = "\n".join([f"• {get_card_emoji(c)} {c}" for c in cards])
            msg = f"🃏 **Your Cards ({len(cards)}):**\n\n{card_list}"
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
    
    if isinstance(game, ClassicGame):
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
    
    elif isinstance(game, CollectionGame):
        current = game.get_current_player()
        next_p = game.get_next_player()
        msg = f"🃏 **COLLECTION MODE STATUS**\n\n"
        msg += f"👥 **Players:** {len(game.players)}\n"
        msg += f"🏆 **Winners:** {len(game.winners)}/{game.get_max_winners()}\n"
        if current:
            msg += f"👑 **Current Turn:** {current['name']}\n"
        if next_p:
            msg += f"➡️ **Next Player:** {next_p['name']}\n"
        
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
        if isinstance(game, ClassicGame):
            role = game.get_player_role(p["id"])
            status = "✅ Found" if p["id"] in game.found_players else "🔄 Active"
            msg += f"{i}. {p['name']} - {role} - {status}\n"
        else:
            cards = game.get_player_cards(p["id"])
            card_count = len(cards) if cards else 0
            msg += f"{i}. {p['name']} - {card_count} cards\n"
    
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
    
    if isinstance(game, ClassicGame):
        if not game.swap_history:
            bot.send_message(chat_id, "📋 No swaps yet!")
        else:
            msg = "🔄 **Swap History:**\n\n"
            for i, swap in enumerate(game.swap_history[-10:], 1):
                msg += f"{i}. {swap['seeker']} → {swap['chosen']}\n"
            bot.send_message(chat_id, msg, parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "📋 History only available in Classic Mode!")

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
    if isinstance(game, ClassicGame):
        game.timer_active = False
    
    bot.send_message(
        chat_id,
        f"💀 **GAME KILLED!**\n\n"
        f"**{message.from_user.first_name}** ended the game!\n"
        f"👥 Final players: {len(game.players)}\n"
        f"📊 Final results:",
        parse_mode='Markdown'
    )
    
    if isinstance(game, ClassicGame):
        show_leaderboard_func(chat_id)
    elif isinstance(game, CollectionGame):
        if game.winners:
            show_collection_winners(chat_id, game)
        else:
            bot.send_message(chat_id, "No winners yet!")
    
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
        bot.send_message(chat_id, "🔄 **Game reset!** Use `/game` or `/collect` to start new.", parse_mode='Markdown')
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
