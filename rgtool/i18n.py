"""Telegram message texts in English and Latvian. Choose with UI_LANG=en|lv in .env.

"KI-market price" is the game's own name for the price the computer (KI) pays.
"""

from __future__ import annotations

MESSAGES = {
    "en": {
        "wh_buyer": "A buyer pays {bid} (KI-market {ki}), sell to them first.",
        "wh_no_buyer": "No better buyer, free up space via the KI-market ({ki}).",
        "wh_full_now": "<b>FULL!</b>", "wh_full_in": "full in ~<b>{t}</b>",
        "mk_line": "• <b>{name}</b> {bid} (+{pct}% above KI-market), in stock {held}, gain up to +{gain}",
        "mk_head": "🏷 <b>Buyers paying above the KI-market</b>",
        "tr_line": "• <b>{name}</b> KI-market price {ki}, +{pct}% above the 7-day average. Stock ≈ {value}",
        "tr_head": "💰 <b>KI-market price rise</b>",
        "new_item": "🚨 <b>NEW ITEM: {name}</b> (ID {id}). KI-market price {ki}. First-day prices are usually the highest. Act now!",
        "mines_now": "Mines now ~{pct}% (forecast)",
        "ms_opened": "🎯 <b>Missions opened</b>",
        "ms_deadline": "⏰ Mission <b>{title}</b> ends in {t}: {progress}/{goal}. Penalty {penalty}!",
        "maint": "🔧 Mines average <b>{avg}%</b> (lowest {min}%), not maintained.",
        "maint_wait": "Maintenance mission opens {when} (in {t}). Wait if you can.",
        "maint_open": "Maintenance mission is open, time for maintenance!",
        "rep_head": "📊 <b>Daily report</b> — {user}",
        "rep_line": "Level {lvl} · Rank {rank} · Points {points}",
        "rep_delta": "{label}: points +{points}, rank {rank}",
        "rep_money": "Money ({date}): +{rev} / −{exp} = {net}",
        "rep_stock": "Warehouse value (KI-market prices): {v}",
        "rep_cond": "Mine condition ~{pct}% (forecast)",
        "rep_soon": "Missions opening in the next 24h:",
        "rep_credits": "API credits: used in 24h {used}",
        "rep_left": ", left {n}",
        "low_credits": "⚠️ Only {n} API credits left. Queries stopped.",
        "no_report": "No data for a report yet.",
    },
    "lv": {
        "wh_buyer": "Pircējs tirgū maksā {bid} (KI-market {ki}), pārdod vispirms viņam.",
        "wh_no_buyer": "Labāka pircēja nav, atbrīvo vietu caur KI-market ({ki}).",
        "wh_full_now": "<b>PILNA!</b>", "wh_full_in": "pilna pēc ~<b>{t}</b>",
        "mk_line": "• <b>{name}</b> {bid} (+{pct}% virs KI-market), krājumā {held}, ieguvums līdz +{gain}",
        "mk_head": "🏷 <b>Pircēji maksā virs KI-market</b>",
        "tr_line": "• <b>{name}</b> KI-market cena {ki}, +{pct}% virs 7d vidējās. Krājumā ≈ {value}",
        "tr_head": "💰 <b>KI-market cenas kāpums</b>",
        "new_item": "🚨 <b>JAUNA PRECE: {name}</b> (ID {id}). KI-market cena {ki}. Pirmās dienas cenas parasti ir augstākās. Rīkojies tagad!",
        "mines_now": "Raktuves šobrīd ~{pct}% (prognoze)",
        "ms_opened": "🎯 <b>Atvērušās misijas</b>",
        "ms_deadline": "⏰ Misija <b>{title}</b> beidzas pēc {t}: {progress}/{goal}. Sods {penalty}!",
        "maint": "🔧 Raktuves vidēji <b>{avg}%</b> (zemākā {min}%), apkope nav veikta.",
        "maint_wait": "Maintenance misija atvērsies {when} (pēc {t}). Ja vari, pagaidi.",
        "maint_open": "Maintenance misija ir atvērta, laiks apkopei!",
        "rep_head": "📊 <b>Dienas atskaite</b> — {user}",
        "rep_line": "Līmenis {lvl} · Rank {rank} · Punkti {points}",
        "rep_delta": "{label}: punkti +{points}, rank {rank}",
        "rep_money": "Nauda ({date}): +{rev} / −{exp} = {net}",
        "rep_stock": "Noliktavas vērtība (KI-market cenās): {v}",
        "rep_cond": "Raktuvju stāvoklis ~{pct}% (prognoze)",
        "rep_soon": "Misijas, kas atvērsies 24h laikā:",
        "rep_credits": "API kredīti: izlietoti 24h {used}",
        "rep_left": ", atlikumā {n}",
        "low_credits": "⚠️ Palikuši tikai {n} API kredīti. Vaicājumi apturēti.",
        "no_report": "Nav datu atskaitei.",
    },
}

_lang = "en"


def set_lang(lang: str) -> None:
    global _lang
    _lang = lang if lang in MESSAGES else "en"


def t(key: str, **p) -> str:
    s = MESSAGES[_lang].get(key) or MESSAGES["en"].get(key) or key
    return s.format(**p) if p else s
