# ============================================
# CARD WARFARE BOT - CONFIGURATION
# ============================================

import os

# ===== BOT SETTINGS =====
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
BOT_OWNER_ID = int(os.environ.get('BOT_OWNER_ID', 123456789))

# ===== GAME SETTINGS =====
TIMER_SECONDS = int(os.environ.get('TIMER_SECONDS', 30))

# ===== DYNAMIC ROLE SYSTEM (For Classic Mode) =====
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

# ===== COLLECTION MODE SETTINGS =====
# Card types used in Collection Mode
CARD_TYPES = [
    "King",
    "Queen", 
    "Minister",
    "Commander",
    "Detective",
    "Spy",
    "Guard",
    "Police Chief",
    "Police",
    "Chor"
]

# Card emojis for Collection Mode
CARD_EMOJIS = {
    "King": "👑",
    "Queen": "👸",
    "Minister": "🧙",
    "Commander": "⚔️",
    "Detective": "🕵️",
    "Spy": "🥷",
    "Guard": "🛡️",
    "Police Chief": "👮",
    "Police": "👮",
    "Chor": "🕵️"
}

# ===== STICKER IDs FOR CARDS (From Card_Warfare_cards pack) =====
CARD_STICKERS = {
    "King": "CAACAgUAAxkBAzxhpmo2Jmhc8BdNST7VrAHG12o-qtlEAAIOJgACNNSxVa5k_ArhDyhYPAQ",
    "Queen": "CAACAgUAAxkBAzxhq2o2Jmr7nuIORKCnzSRMn7gYKvuZAALiIwACYlOwVbpYv1od03b_PAQ",
    "Minister": "CAACAgUAAxkBAzxhrWo2Jmu_h8nJDmI6nrrxmIBYRcYbAAJVJAACx8KwVSAF-ha-zFZEPAQ",
    "Commander": "CAACAgUAAxkBAzxhv2o2JmyA0QXh_RCBaNHZnrG0n4qdAAJ7HQACxRq5VYdVeBufm10yPAQ",
    "Detective": "CAACAgUAAxkBAzxhsWo2Jm3a3jOZbYT5Zd9jSiCY9ePDAAL-IgACfxWxVRL7TiKJOL8IPAQ",
    "Spy": "CAACAgUAAxkBAzxhs2o2Jm7WX4AIFaqPKtPtKjgIh_yXAAIsHQACa_O5VXxKjOV2V1-OPAQ",
    "Guard": "CAACAgUAAxkBAzxhtWo2Jm-nZ4Rps1IKLf-xnXF_27mdAAKNIQAC98qxVRSgUQN1Y95SPAQ",
    "PoliceChief": "CAACAgUAAxkBAzxht2o2JnDXBvd2_hOo0VimSvD7KVXfAAKqJAACaGuwVQIJUWhF90WXPAQ",
    "Police": "CAACAgUAAxkBAzxhumo2JnHupi8hjpgTjwAB027cYejEJgACzBwAAjlAuFU02_b9637hrTwE",
    "Chor": "CAACAgUAAxkBAzxhvGo2JnI7RIR7xTKL3qsWsHQn7UwxAAI7HAACU4uwVR5M0QL0ubMcPAQ",
    "CardBack": "CAACAgUAAxkBAzxhvmo2JnMLGxsQO2HxH8lCRZPn-E11AAK6HAACrgexVfbbEX13mB0LPAQ"
}

# ===== COLLECTION MODE CARD TYPES BY PLAYER COUNT =====
def get_card_types_for_collection(player_count):
    """
    Get card types for Collection Mode based on number of players.
    """
    all_types = ["King", "Queen", "Minister", "Commander", "Detective", "Spy", "Guard", "Police", "Chor"]
    
    if player_count == 4:
        return ["King", "Queen", "Police", "Chor"]
    elif player_count == 5:
        return ["King", "Queen", "Minister", "Police", "Chor"]
    else:
        return all_types[:player_count]

# ===== DYNAMIC ROLE SYSTEM (For Classic Mode) =====
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

def get_card_type_emoji(card_type):
    """Get emoji for a card type"""
    return CARD_EMOJIS.get(card_type, "🃏")

def get_card_sticker(card_type):
    """Get sticker ID for a card type"""
    return CARD_STICKERS.get(card_type)

# ===== WINNER SETTINGS =====
def get_max_winners(player_count):
    """
    Get maximum number of winners based on player count.
    4 players → 1 winner
    5 players → 2 winners
    6-10 players → 3 winners
    """
    if player_count == 4:
        return 1
    elif player_count == 5:
        return 2
    else:
        return 3

# ===== EMOJIS =====
EMOJIS = {
    "correct": "✅",
    "wrong": "❌",
    "swap": "🔄",
    "timer": "⏱️",
    "trophy": "🏆",
    "warning": "⚠️",
    "card": "🃏",
    "collection": "🃏"
}
