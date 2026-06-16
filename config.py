import os

# ===== BOT SETTINGS =====
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
BOT_OWNER_ID = int(os.environ.get('BOT_OWNER_ID', 123456789))

# ===== GAME SETTINGS =====
TIMER_SECONDS = int(os.environ.get('TIMER_SECONDS', 30))
STARTING_COINS = int(os.environ.get('STARTING_COINS', 100))
MIN_BET = int(os.environ.get('MIN_BET', 10))
MAX_BET = int(os.environ.get('MAX_BET', 50))

# ===== MODE CONFIGURATION =====
MODES = {
    4: {
        "name": "4-Player",
        "roles": ["👑 King", "👸 Queen", "👮 Police", "🕵️ Chor"],
        "points": [100, 80, 50],
        "targets": ["Queen", "Police", "Chor"]
    },
    6: {
        "name": "6-Player", 
        "roles": ["👑 King", "👸 Queen", "🧙 Minister", "⚔️ Commander", "👮 Police", "🕵️ Chor"],
        "points": [100, 90, 80, 70, 50],
        "targets": ["Queen", "Minister", "Commander", "Police", "Chor"]
    },
    8: {
        "name": "8-Player",
        "roles": ["👑 King", "👸 Queen", "🧙 Minister", "⚔️ Commander", "🕵️ Detective", "👮 Police", "🥷 Spy", "🕵️ Chor"],
        "points": [100, 90, 80, 70, 60, 50, 40],
        "targets": ["Queen", "Minister", "Commander", "Detective", "Police", "Spy", "Chor"]
    },
    10: {
        "name": "10-Player (Epic)",
        "roles": ["👑 King", "👸 Queen", "🧙 Minister", "⚔️ Commander", "👮 Police Chief", "🕵️ Detective", "🥷 Spy", "🛡 Guard", "👮 Police", "🕵️ Chor"],
        "points": [100, 90, 80, 70, 60, 50, 40, 30, 20],
        "targets": ["Queen", "Minister", "Commander", "Police Chief", "Detective", "Spy", "Guard", "Police", "Chor"]
    }
}

# ===== SHOP ITEMS =====
SHOP = {
    "shield": {"name": "🛡️ Shield", "cost": 20, "effect": "No swap on wrong guess"},
    "hint": {"name": "🎯 Hint", "cost": 40, "effect": "Get a clue about target"},
    "freeze": {"name": "⏱️ Time Freeze", "cost": 25, "effect": "Pause timer for 10s"},
    "double": {"name": "🔍 Double Chance", "cost": 30, "effect": "2 guesses in one turn"},
}

# ===== EMOJIS =====
EMOJIS = {
    "correct": "✅",
    "wrong": "❌",
    "swap": "🔄",
    "timer": "⏱️",
    "coins": "💰",
    "points": "⭐",
    "trophy": "🏆",
    "warning": "⚠️"
}
