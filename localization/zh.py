# Chinese Mandarin (zh) mechanics dictionary for Hikayat

ITEM_ICON_KEYWORDS = {
    # 0. Digital Media Items
    "digital_video": ("视频", "录像", "片段"),
    "digital_photo": ("照片", "相片", "自拍"),

    # 1. Accessories
    "accessories": ("戒指", "指环", "手镯", "手链"),
    "amulet": ("项链", "护身符", "吊坠", "法珠", "符咒"),

    # 2. Weapons & Tools
    "phone": ("手机", "智能手机"),
    "backpack": ("背包", "行囊", "布袋", "包裹"),
    "wand": ("法杖", "魔杖", "权杖"),
    "grimoire": ("法术书", "秘典", "魔导书", "古卷", "经卷"),
    "bow": ("长弓", "短弓", "弓", "弩", "十字弩"),
    "gun": ("火枪", "手枪", "步枪", "猎枪"),
    "dagger": ("匕首", "短刀", "短剑", "飞刀", "马来短剑", "短怀剑"),
    "axe": ("战斧", "斧", "板斧", "手斧"),
    "hammer": ("战锤", "铁锤", "大锤", "重锤"),
    "spear": ("长枪", "长矛", "战戟", "三叉戟", "标枪"),
    "whip": ("长鞭", "皮鞭", "锁链"),
    "sword": ("长剑", "铁剑", "宝剑", "短剑", "巨剑", "大剑", "太刀", "弯刀", "剑"),

    # 3. Clothing / Armor / Headwear
    "crown": ("王冠", "皇冠", "头冠", "冕"),
    "glasses": ("眼镜", "目镜"),
    "top_hat": ("礼帽", "高顶礼帽"),
    "helm": ("头盔", "面具", "兜帽", "战盔"),
    "cap": ("便帽", "帽子"),
    "boots": ("长靴", "战靴", "皮靴", "鞋", "靴子", "凉鞋"),
    "gloves": ("手套", "护手", "铁手套", "臂铠"),
    "pants": ("裤子", "长裤", "护腿", "裙"),
    "armor": (
        "板甲", "盔甲", "锁子甲", "战甲", "长袍", "法袍", "外衣", "胸甲", "皮甲", "大衣", "制服", "衬衫", "和服", "羽织", "卡巴雅", "宋吉锦"
    ),
    "shield": ("盾牌", "圆盾", "大盾", "重盾", "盾"),

    # 4. Slot Type Fallbacks
    "slot_weapon": ("武器",),
    "slot_shield": ("盾牌",),
    "slot_head": ("头部", "头盔"),
    "slot_bottom": ("下装", "裤子"),
    "slot_gloves": ("手套",),
    "slot_shoes": ("鞋子",),
    "slot_top": ("上装",),
    "slot_armor": ("护甲", "盔甲"),

    # 5. Consumables & Quest Items
    "boba": ("奶茶", "珍珠奶茶"),
    "coffee": ("咖啡",),
    "tea": ("茶", "绿茶", "红茶"),
    "wine": ("葡萄酒", "红酒"),
    "beer": ("啤酒", "麦酒"),
    "drink": ("饮料", "清水", "泉水"),
    "food": ("食物", "干粮", "面包", "肉"),
    "health": ("治疗", "生命", "绷带", "金创药", "伤药"),
    "mana": ("法力", "魔力", "法力药水"),
    "potion": ("药水", "药剂", "秘药", "灵药", "疯柑", "净盐", "线香", "黄瓜", "油豆腐", "符箓", "寒铁护符"),
    "quest": ("钥匙", "地图", "密信", "卷轴", "信件", "古籍", "信函", "狐火铜铃", "竹笛", "传世圣物", "铃铛", "suzu", "serunai", "pusaka"),
}

TWO_HANDED_ARCHETYPES = (
    "双手剑", "巨剑", "大剑", "战戟", "长矛", "双手战锤", "长弓", "十字弩", "重火枪"
)

TWO_HANDED_KEYWORDS = (
    "双手", "巨剑", "大剑", "双手剑", "战戟", "长弓", "弩", "重锤"
)

ITEM_LEMMAS = {
    "weapons": [
        "剑", "长剑", "铁剑", "宝剑", "短刀", "匕首", "战斧", "长枪", "长矛", "战锤", "长弓", "弩", "法杖", "火枪"
    ],
    "shields": [
        "盾", "盾牌", "圆盾", "重盾"
    ],
    "head": [
        "头盔", "战盔", "兜帽", "面具", "王冠"
    ],
    "armor": [
        "盔甲", "板甲", "锁子甲", "胸甲", "长袍", "战甲", "皮甲"
    ],
    "pants": [
        "裤子", "长裤", "护腿"
    ],
    "gloves": [
        "手套", "护手", "臂铠"
    ],
    "shoes": [
        "战靴", "长靴", "皮靴", "鞋子"
    ],
    "accessories": [
        "戒指", "护身符", "项链", "手镯", "法珠"
    ],
    "usables": [
        "药水", "治疗药水", "法力药水", "干粮", "面包", "肉", "茶", "水", "酒"
    ],
    "tomes_and_quests": [
        "卷轴", "秘典", "古卷", "钥匙", "地图", "信件", "密信"
    ],
}

ENEMY_AFFIXES = {
    "Volatile": "易爆",
    "Overclocked": "超频",
    "Vampiric": "吸血",
    "Phasing": "相位",
    "Corrosive": "腐蚀",
    "Grounded": "绝缘",
    "Hydro-Shielded": "水盾",
    "Tempest-Wreathed": "风暴缠绕",
}

REVERSE_ENEMY_AFFIXES = {v.lower(): k for k, v in ENEMY_AFFIXES.items()}

DIALOGUE_EXIT_PHRASES = (
    "道别并离开", "离开交谈", "告辞", "告别", "结束对话", "转身离开", "离去", "退下", "就此别过"
)

DIALOGUE_INIT_PREFIXES = (
    "上前交谈", "走近交谈", "打招呼", "询问", "走近并交谈", "商讨", "拜访", "搭话"
)

MOVEMENT_PREFIXES = (
    "前往", "去往", "走进", "进入", "动身前往", "返回"
)


REALTY_LABELS = {
    "app_name": "房产与地契",
    "app_sub": "安全屋与备用钥匙",
    "tab_owned": "我的居所",
    "tab_market": "房产挂牌",
    "badge_starter": "初始宿舍",
    "badge_owned": "私人房产",
    "badge_for_sale": "待售",
    "primary_home": "主要居所",
    "set_primary": "设为主宅",
    "buy_deed": "购买地契",
    "deed_owned": "已拥有",
    "give_spare_key": "赠送钥匙",
    "revoke_key": "收回钥匙",
    "spare_keys_label": "备用钥匙持有人",
    "starter_spare_key_note": "阵营分配宿舍会随转职迁移。购买永久房契后可向亲密联系人赠送备用钥匙。",
    "no_deeds_owned": "尚未拥有任何永久房产地契。",
    "no_eligible_contacts": "好感度达到 70+ 或建立恋人关系后可赠送备用钥匙。",
    "purchased_ok": "成功购入房产地契！",
    "purchase_failed": "购房失败。",
    "primary_updated": "主要居所已更新。",
    "key_granted": "已赠送备用钥匙！",
    "key_revoked": "已收回备用钥匙。",
}


FOLKLORE_SANCTUARY_LABELS = {
    "kitsune_spirit_merchant": "稻荷灵药铺",
    "bunian_pusaka_merchant": "传世圣物匠师馆",
    "ranger_station_outfitter": "林区护林补给商",
    "spirit_relay_badge": "灵脉传讯",
    "veil_unattuned_badge": "凡俗门径",
    "veil_attuned_badge": "灵障已共鸣",
    "twilight_veil_badge": "逢魔时刻·灵障渐薄",
    "leyline_passage_badge": "灵脉秘径",
    "sanctuary_pact_warning": "已违背灵境互不侵犯盟约——请于外门奉上 100 金币赎罪供奉。",
}


QUEST_UI_LABELS = {
    "main_objective": "核心主目标",
    "optional_routes": "可选战术路线",
    "peak_chapter": "高潮大场面",
    "chronicle_tapestry": "纪年史挂毯",
    "fallen_world_ch11": "沦陷世界 — 第11章抵抗军尾声",
    "peak_scar": "高潮创痕",
    "liberation_op": "光复行动",
    "optional_aid": "战术援助",
    "optional_bypass": "潜入绕行",
    "optional_alternative": "替代路线",
    "optional_threatened": "危机营救 / 撤离",
    "bonus_claimed": "奖励已领取",
    "failed_route": "路线失败",
    "locked_out": "已封锁",
    "fallen_world_epilogue": "沦陷世界 — 抵抗军尾声",
    "base_reward_note": "基础达成奖励",
    "threat_clock": "威胁时钟",
    "threat_paused": "已暂停（决战）",
    "threat_dormant": "章节未触发前暂不计时",
    "threat_reinforced": "敌方增援",
    "threat_scar_pending": "章节创痕风险",
    "clue_sources": "线索途径",
    "source_open": "可查探",
    "source_burned": "已失手",
    "source_cold": "已中断",
    "source_claimed": "已获取",
    "source_bonus": "额外线索",
}

PACT_UI_LABELS = {
    "title": "异界契约与恶魔盟约",
    "subtitle": "零魔耗契约 • 鲜血与供奉账册",
    "tab_active": "当前盟约",
    "tab_discover": "寻访与相性审定",
    "tab_compendium": "契约主图鉴",
    "slots_label": "契约槽位",
    "remote_ready": "可进行远程通灵仪式",
    "remote_blocked": "需脱离战斗并身处圣所或安全居所",
    "appraisal_favored": "眷顾（0.65倍代价 • 直开二/三阶）",
    "appraisal_neutral": "中立（1.0倍标准条款）",
    "appraisal_disdained": "厌弃（1.50倍代价 • 封锁三阶）",
    "sign_btn": "缔结盟约",
    "upgrade_btn": "深化位阶",
    "feed_btn": "通灵供奉 / 偿清血债",
    "sever_scrub_btn": "医疗 / 神社净除",
    "sever_exorcism_btn": "迎战显化体（驱魔断契）",
    "pact_bound_badge": "[契约绑定]",
    "lethal_overdraw": "致命透支（欠下血债）",
    "breach_stage_1": "神明震怒 — 24小时血债追索",
    "breach_stage_2": "暴烈断契 — 灵魂创痕",
    "contracted_badge": "已缔约",
    "currently_bound": "契约中",
}
