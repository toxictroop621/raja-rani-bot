# ============================================
# DATABASE.PY - All database operations
# ============================================

import json
import os
from datetime import datetime

# ===== FILE PATHS =====
DATA_DIR = "data"
GAME_DATA_FILE = os.path.join(DATA_DIR, "game_data.json")
PLAYER_DATA_FILE = os.path.join(DATA_DIR, "player_data.json")
USER_DATABASE_FILE = os.path.join(DATA_DIR, "user_database.json")

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ============================================
# USER DATABASE - Stores ALL users who interact
# ============================================

def load_user_database():
    """Load user database from file"""
    try:
        with open(USER_DATABASE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_database(user_db):
    """Save user database to file"""
    try:
        with open(USER_DATABASE_FILE, "w") as f:
            json.dump(user_db, f, indent=2)
    except:
        pass

def register_user(user_id, username, first_name, last_name="", user_db=None):
    """Register a user in the database"""
    if user_db is None:
        user_db = load_user_database()
    
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
        # Update last active and username
        user_db[user_id_str]["last_active"] = datetime.now().isoformat()
        if username:
            user_db[user_id_str]["username"] = username
        save_user_database(user_db)
        return False, user_db

def find_user_by_name_or_username(search_term, user_db):
    """
    Find a user by:
    - @username
    - first_name
    - last_name
    - full name
    - partial match
    """
    search_term = search_term.replace('@', '').strip().lower()
    
    if not user_db:
        return None, None
    
    # 1. Search by username (exact match)
    for uid, data in user_db.items():
        if data.get("username", "").lower() == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    # 2. Search by first_name (exact match)
    for uid, data in user_db.items():
        if data.get("first_name", "").lower() == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    # 3. Search by full name (first + last)
    for uid, data in user_db.items():
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip().lower()
        if full_name == search_term:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    # 4. Partial match (for group mentions without @)
    for uid, data in user_db.items():
        first_name = data.get("first_name", "").lower()
        username = data.get("username", "").lower()
        if search_term in first_name or search_term in username:
            return int(uid), data.get("username") or data.get("first_name", "User")
    
    return None, None

def get_user_data(user_id, user_db):
    """Get user data from database"""
    user_id_str = str(user_id)
    return user_db.get(user_id_str)

def get_all_users(user_db):
    """Get all users in database"""
    return list(user_db.values())

def get_user_count(user_db):
    """Get total number of registered users"""
    return len(user_db)

# ============================================
# PLAYER STATS - Game stats for players
# ============================================

def load_player_data():
    """Load player stats from file"""
    try:
        with open(PLAYER_DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_player_data(player_data):
    """Save player stats to file"""
    try:
        with open(PLAYER_DATA_FILE, "w") as f:
            json.dump(player_data, f, indent=2)
    except:
        pass

def get_player_stats(player_id, player_data, STARTING_COINS):
    """Get or create player stats"""
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
        save_player_data(player_data)
    return player_data[str(player_id)]

# ============================================
# GAME DATA - Active games
# ============================================

def load_game_data():
    """Load game data from file"""
    try:
        with open(GAME_DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"games": {}, "history": {}}

def save_game_data(game_data):
    """Save game data to file"""
    try:
        with open(GAME_DATA_FILE, "w") as f:
            json.dump(game_data, f, indent=2)
    except:
        pass
