class SourceDevice:
    UNKNOWN = "unknown"
    MININO = "minino"
    FLIPPER_DEV_BOARD = "flipper dev board"
    FLIPPER_DEV_BOARD_PRO = "flipper dev board pro"
    MARAUDER_V4 = "marauder v4"
    MARAUDER_V6 = "marauder v6"
    FLIPPER_BFFB = "flipper bffb"
    MARAUDER_ESP32 = "marauder esp32"
    OTHER = "other"

    CHOICES = [
        (UNKNOWN, UNKNOWN),
        (MININO, MININO),
        (FLIPPER_DEV_BOARD, FLIPPER_DEV_BOARD),
        (FLIPPER_DEV_BOARD_PRO, FLIPPER_DEV_BOARD_PRO),
        (MARAUDER_V4, MARAUDER_V4),
        (MARAUDER_V6, MARAUDER_V6),
        (FLIPPER_BFFB, FLIPPER_BFFB),
        (MARAUDER_ESP32, MARAUDER_ESP32),
        (OTHER, OTHER),
    ]
