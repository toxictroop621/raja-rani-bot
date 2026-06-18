# ============================================
# CARD WARFARE BOT - CONFIGURATION
# ============================================

import os

# ===== BOT SETTINGS =====
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
BOT_OWNER_ID = int(os.environ.get('BOT_OWNER_ID', 123456789))

# ===== GAME SETTINGS =====
TIMER_SECONDS = int(os.environ.get('TIMER_SECONDS', 30))

# ===== DYNAMIC ROLE SYSTEM =====
# Roles in order (Chor is always last)
ALL_ROLES = [
    "👑 King",
    "👸 Queen",
    "🧙 Minister",
    "⚔️ Commander",
    "🕵️ Detective",
    "🥷 Spy",
    "🛡 Guard",
    "👮 Police Chief",
    "👮 Police",
    "🕵️ Chor"
]

# Points for each level (decreasing)
ALL_POINTS = [100, 90, 80, 70, 60, 50, 40, 30, 20]

def get_roles_for_players(player_count):
    """
    Get roles and points based on number of players.
    Minimum: 4, Maximum: 10
    """
    if player_count < 4:
        return None, None
    
    if player_count > 10:
        player_count = 10
    
    # Get first (player_count - 1) roles, then add Chor at the end
    roles = ALL_ROLES[:player_count - 1] + ["🕵️ Chor"]
    points = ALL_POINTS[:player_count - 1]
    
    return roles, points

# ===== EMOJIS =====
EMOJIS = {
    "correct": "✅",
    "wrong": "❌",
    "swap": "🔄",
    "timer": "⏱️",
    "trophy": "🏆",
    "warning": "⚠️"
}
