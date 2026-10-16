// constants.js - 職業、種族、伺服器、賽季的顯示資料

const ICON_BASE = 'https://wow.zamimg.com/images/wow/icons/medium/';

export const CLASSES = {
  1:  { name: '戰士',     color: '#C69B6D', icon: 'classicon_warrior' },
  2:  { name: '聖騎士',   color: '#F48CBA', icon: 'classicon_paladin' },
  3:  { name: '獵人',     color: '#AAD372', icon: 'classicon_hunter' },
  4:  { name: '盜賊',     color: '#FFF468', icon: 'classicon_rogue' },
  5:  { name: '牧師',     color: '#FFFFFF', icon: 'classicon_priest' },
  6:  { name: '死亡騎士', color: '#C41E3A', icon: 'classicon_deathknight' },
  7:  { name: '薩滿',     color: '#0070DD', icon: 'classicon_shaman' },
  8:  { name: '法師',     color: '#3FC7EB', icon: 'classicon_mage' },
  9:  { name: '術士',     color: '#8788EE', icon: 'classicon_warlock' },
  10: { name: '武僧',     color: '#00FF98', icon: 'classicon_monk' },
  11: { name: '德魯伊',   color: '#FF7C0A', icon: 'classicon_druid' },
};

export const RACES = {
  1:  { name: '人類',   icon: 'race_human_male' },
  2:  { name: '獸人',   icon: 'race_orc_male' },
  3:  { name: '矮人',   icon: 'race_dwarf_male' },
  4:  { name: '夜精靈', icon: 'race_nightelf_male' },
  5:  { name: '不死族', icon: 'race_scourge_male' },
  6:  { name: '牛頭人', icon: 'race_tauren_male' },
  7:  { name: '地精',   icon: 'race_gnome_male' },
  8:  { name: '食人妖', icon: 'race_troll_male' },
  9:  { name: '哥布林', icon: 'race_goblin_male' },
  10: { name: '血精靈', icon: 'race_bloodelf_male' },
  11: { name: '德萊尼', icon: 'race_draenei_male' },
  22: { name: '狼人',   icon: 'race_worgen_male' },
  24: { name: '熊貓人', icon: 'race_pandaren_male' },
  25: { name: '熊貓人', icon: 'race_pandaren_male' },
  26: { name: '熊貓人', icon: 'race_pandaren_male' },
};

export const REALMS = {
  'ivus': '伊弗斯',
  'golemagg': '古雷曼格',
  'maraudon': '瑪拉頓',
  'windseeker': '逐風者',
  'arathi-basin': '阿拉希盆地',
  'wushoolay': '烏蘇雷',
  'zeliek': '札里克',
  'murloc': '魚人',
};

export const FACTIONS = {
  HORDE: { name: '部落' },
  ALLIANCE: { name: '聯盟' },
};

export const BRACKETS = {
  '2v2': '2v2',
  '3v3': '3v3',
  '5v5': '5v5',
  'rbg': '積分戰場',
};

export const SEASONS = {
  1:  { expansion: '燃燒的遠征', title: '煉獄 Infernal' },
  2:  { expansion: '燃燒的遠征', title: '殘忍 Merciless' },
  3:  { expansion: '燃燒的遠征', title: '復仇 Vengeful' },
  4:  { expansion: '燃燒的遠征', title: '野蠻 Brutal' },
  5:  { expansion: '巫妖王之怒', title: '致命 Deadly' },
  6:  { expansion: '巫妖王之怒', title: '狂烈 Furious' },
  7:  { expansion: '巫妖王之怒', title: '無情 Relentless' },
  8:  { expansion: '巫妖王之怒', title: '憤怒 Wrathful' },
  9:  { expansion: '浩劫與重生', title: '兇惡 Vicious' },
  10: { expansion: '浩劫與重生', title: '殘酷 Ruthless' },
  11: { expansion: '浩劫與重生', title: '絕命 Cataclysmic' },
  12: { expansion: '潘達利亞之謎', title: '狠毒 Malevolent' },
  13: { expansion: '潘達利亞之謎', title: '暴君 Tyrannical' },
  14: { expansion: '潘達利亞之謎', title: '暴虐 Grievous' },
};

export const iconUrl = name => ICON_BASE + name + '.jpg';
export const realmName = slug => REALMS[slug] || slug || '-';
