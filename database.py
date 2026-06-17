# ============================================
# DATABASE.PY - MongoDB Connection (Fixed SSL)
# ============================================

import os
from datetime import datetime
import pymongo
from pymongo import MongoClient

# ===== MONGODB CONNECTION =====

def get_db():
    """Get MongoDB database connection"""
    MONGO_URI = os.environ.get('MONGO_URI')
    if not MONGO_URI:
        print("⚠️ MONGO_URI not set, using local data")
        return None
    
    try:
        # Add SSL parameters to fix handshake error
        client = MongoClient(
            MONGO_URI,
            ssl=True,
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=5000
        )
        # Force a connection to check if it works
        client.admin.command('ping')
        print("✅ MongoDB connection successful!")
        db = client.get_database("card_warfare_bot")
        return db
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return None

def init_collections():
    """Initialize collections if they don't exist"""
    try:
        db = get_db()
        if db is None:
            print("⚠️ No database connection, skipping initialization")
            return None
        
        # Collections
        if "users" not in db.list_collection_names():
            db.create_collection("users")
            print("✅ Created 'users' collection")
        
        if "players" not in db.list_collection_names():
            db.create_collection("players")
            print("✅ Created 'players' collection")
        
        if "games" not in db.list_collection_names():
            db.create_collection("games")
            print("✅ Created 'games' collection")
        
        # Create indexes
        db.users.create_index("user_id", unique=True)
        db.players.create_index("player_id", unique=True)
        db.games.create_index("chat_id")
        
        print("✅ MongoDB collections initialized!")
        return db
    except Exception as e:
        print(f"❌ MongoDB initialization failed: {e}")
        return None

# ============================================================
# USER DATABASE FUNCTIONS
# ============================================================

def load_user_database():
    """Load all users from MongoDB"""
    try:
        db = get_db()
        if db is None:
            return {}
        users = db.users.find()
        result = {}
        for user in users:
            result[str(user["user_id"])] = {
                "id": user["user_id"],
                "username": user.get("username", ""),
                "first_name": user.get("first_name", ""),
                "last_name": user.get("last_name", ""),
                "registered_at": user.get("registered_at"),
                "last_active": user.get("last_active")
            }
        print(f"✅ Loaded {len(result)} users from MongoDB")
        return result
    except Exception as e:
        print(f"❌ Error loading users: {e}")
        return {}

def save_user_database(user_db):
    """Save all users to MongoDB"""
    try:
        db = get_db()
        if db is None:
            return
        db.users.delete_many({})
        
        for uid, data in user_db.items():
            doc = {
                "user_id": int(uid),
                "username": data.get("username", ""),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "registered_at": data.get("registered_at"),
                "last_active": data.get("last_active")
            }
            db.users.insert_one(doc)
        print(f"✅ Saved {len(user_db)} users to MongoDB")
    except Exception as e:
        print(f"❌ Error saving users: {e}")

def register_user(user_id, username, first_name, last_name="", user_db=None):
    """Register a user in the database"""
    user_db = load_user_database() if user_db is None else user_db
    
    user_id_str = str(user_id)
    
    if user_id_str not in user_db:
        user_db[user_id_str] = {
            "id": user_id,
            "username": username or "",
            "first_name": first_name or "",
            "last_name": last_name or "",
            "registered_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat()
        }
        save_user_database(user_db)
        return True, user_db
    else:
        user_db[user_id_str]["last_active"] = datetime.now().isoformat()
        if username:
            user_db[user_id_str]["username"] = username
        save_user_database(user_db)
        return False, user_db

def find_user_by_name_or_username(search_term, user_db):
    search_term = search_term.replace('@', '').strip().lower()
    
    if not user_db:
        return None, None
    
    for uid, data in user_db.items():
        if data.get("username", "").lower() == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    for uid, data in user_db.items():
        if data.get("first_name", "").lower() == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    for uid, data in user_db.items():
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip().lower()
        if full_name == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    for uid, data in user_db.items():
        first_name = data.get("first_name", "").lower()
        username = data.get("username", "").lower()
        if search_term in first_name or search_term in username:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    return None, None

# ============================================================
# PLAYER STATS FUNCTIONS
# ============================================================

def load_player_data():
    """Load all player stats from MongoDB"""
    try:
        db = get_db()
        if db is None:
            return {}
        players = db.players.find()
        result = {}
        for player in players:
            result[str(player["player_id"])] = {
                "coins": player.get("coins", 100),
                "points": player.get("points", 0),
                "wins": player.get("wins", 0),
                "games": player.get("games", 0),
                "streak": player.get("streak", 0),
                "correct_guesses": player.get("correct_guesses", 0),
                "wrong_guesses": player.get("wrong_guesses", 0),
                "swaps_survived": player.get("swaps_survived", 0),
                "last_daily": player.get("last_daily"),
                "badges": player.get("badges", []),
                "total_correct": player.get("total_correct", 0),
                "name": player.get("name")
            }
        print(f"✅ Loaded {len(result)} players from MongoDB")
        return result
    except Exception as e:
        print(f"❌ Error loading players: {e}")
        return {}

def save_player_data(player_data):
    """Save all player stats to MongoDB"""
    try:
        db = get_db()
        if db is None:
            return
        db.players.delete_many({})
        
        for pid, stats in player_data.items():
            doc = {
                "player_id": int(pid),
                "coins": stats.get("coins", 100),
                "points": stats.get("points", 0),
                "wins": stats.get("wins", 0),
                "games": stats.get("games", 0),
                "streak": stats.get("streak", 0),
                "correct_guesses": stats.get("correct_guesses", 0),
                "wrong_guesses": stats.get("wrong_guesses", 0),
                "swaps_survived": stats.get("swaps_survived", 0),
                "last_daily": stats.get("last_daily"),
                "badges": stats.get("badges", []),
                "total_correct": stats.get("total_correct", 0),
                "name": stats.get("name")
            }
            db.players.insert_one(doc)
        print(f"✅ Saved {len(player_data)} players to MongoDB")
    except Exception as e:
        print(f"❌ Error saving players: {e}")

def get_player_stats(player_id, STARTING_COINS):
    """Get or create player stats"""
    try:
        db = get_db()
        if db is None:
            return {
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
        
        player = db.players.find_one({"player_id": player_id})
        
        if not player:
            player = {
                "player_id": player_id,
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
            db.players.insert_one(player)
            print(f"✅ Created new player: {player_id}")
        
        return {
            "coins": player.get("coins", STARTING_COINS),
            "points": player.get("points", 0),
            "wins": player.get("wins", 0),
            "games": player.get("games", 0),
            "streak": player.get("streak", 0),
            "correct_guesses": player.get("correct_guesses", 0),
            "wrong_guesses": player.get("wrong_guesses", 0),
            "swaps_survived": player.get("swaps_survived", 0),
            "last_daily": player.get("last_daily"),
            "badges": player.get("badges", []),
            "total_correct": player.get("total_correct", 0),
            "name": player.get("name")
        }
    except Exception as e:
        print(f"❌ Error getting player stats: {e}")
        return {
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

def update_player_stats(player_id, updates):
    """Update a player's stats"""
    try:
        db = get_db()
        if db is None:
            return
        db.players.update_one(
            {"player_id": player_id},
            {"$set": updates}
        )
    except Exception as e:
        print(f"❌ Error updating player stats: {e}")

# ============================================================
# GAME DATA FUNCTIONS
# ============================================================

def load_game_data():
    """Load game data from MongoDB"""
    try:
        db = get_db()
        if db is None:
            return {"games": {}, "history": {}}
        games = db.games.find()
        result = {"games": {}, "history": {}}
        
        for game in games:
            chat_id = str(game["chat_id"])
            result["games"][chat_id] = {
                "mode": game.get("mode", 4),
                "players": game.get("players", []),
                "roles": game.get("roles", []),
                "current_level": game.get("current_level", 0),
                "status": game.get("status", "waiting"),
                "card_map": game.get("card_map", {}),
                "swap_history": game.get("swap_history", []),
                "creator_id": game.get("creator_id"),
                "found_players": game.get("found_players", [])
            }
        print(f"✅ Loaded {len(result['games'])} games from MongoDB")
        return result
    except Exception as e:
        print(f"❌ Error loading games: {e}")
        return {"games": {}, "history": {}}

def save_game_data(game_data):
    """Save game data to MongoDB"""
    try:
        db = get_db()
        if db is None:
            return
        db.games.delete_many({})
        
        games = game_data.get("games", {})
        for chat_id, game in games.items():
            doc = {
                "chat_id": int(chat_id),
                "mode": game.get("mode", 4),
                "players": game.get("players", []),
                "roles": game.get("roles", []),
                "current_level": game.get("current_level", 0),
                "status": game.get("status", "waiting"),
                "card_map": game.get("card_map", {}),
                "swap_history": game.get("swap_history", []),
                "creator_id": game.get("creator_id"),
                "found_players": game.get("found_players", [])
            }
            db.games.insert_one(doc)
        print(f"✅ Saved {len(games)} games to MongoDB")
    except Exception as e:
        print(f"❌ Error saving games: {e}")
