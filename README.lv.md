# RESOURCES Tool

[English](README.md) · **Latviešu**

Lokāls datu savācējs, Telegram brīdinājumi un web pārskats uz atrašanās vietu
balstītajai ekonomikas spēlei [RESOURCES](https://www.resources-game.ch),
izmantojot spēles oficiālo datu API.

> **Par projektu**
> - Šis ir **mācību projekts**: to veidoju, lai mācītos Python, SQLite un nelielas
>   web aplikācijas, un lai spēlētu nedaudz gudrāk.
> - Tas paredzēts darbināšanai **tikai savā datorā**. Nav servera, nav pieslēgšanās
>   un nav mākoņa: tava API atslēga un spēles dati paliek tavā datorā.
> - Tas ir **neoficiāls** un nav saistīts ar spēles izstrādātāju vai viņa atbalstīts.
> - Katrs API vaicājums maksā **API kredītus**, kurus pērc spēlē. Pirms palaišanas
>   izlasi sadaļu par kredītiem.
> - Skaitļi ir aprēķini no API datiem un spēlē izmērītām formulām. Pirms lieliem
>   lēmumiem spēlē pārbaudi tos.

## Ko tas dara

**Savācējs** (`collector.py`) pēc grafika ielādē tavus datus, glabā vēsturi lokālā
SQLite datubāzē un sūta Telegram brīdinājumus:

| | |
|---|---|
| 🚨 Jauna prece | Spēles atjauninājums pievienoja resursu vai produktu. Pirmās dienas cenas bieži ir daudz augstākas |
| 📦 Noliktava | Pilna pēc mazāk nekā 6 h, ar ieteikumu: pārdot spēlētājam virs KI-market cenas vai KI-market |
| 🏷 Pircēji virs KI-market | Izdevīgākie spēlētāju pirkšanas pieprasījumi, katrs paziņots vienreiz |
| 💰 KI-market cenas kāpums | KI-market cena krietni virs 7 dienu vidējās |
| 🎯 Atvērušās misijas | Precīzs atvēršanās laiks no misijas taimera, bez papildu vaicājumiem |
| ⏰ Misijas termiņš | Misija drīz beidzas, bet mērķis nav sasniegts (rāda sodu) |
| 🔧 Apkope | Raktuves zem iestatītā stāvokļa un nav apkoptas, sasaistīts ar Maintenance misiju |
| 📊 Dienas atskaite | Punktu un vietas izmaiņas, nauda, noliktavas vērtība, raktuvju stāvoklis, drīz atveramās misijas |

**Pārskats** (`python -m web.app`) rāda pašreizējo stāvokli latviski vai angliski:
galvenos skaitļus, sarakstu "darāmais tagad", noliktavu (pildījums, laiks līdz pilnai,
pircēja cena), raktuvju karti ar rūpnīcu vajadzību segumu, rūpnīcu peļņu ar reālo
noslodzi, investīciju atmaksāšanos (rūpnīcu uzlabojumi, TU uz raktuvēm), pārstrādes
vērtību, speciālo ēku uzlabojumu progresu, misijas, naudu un nepabeigtos sasniegumus.

*KI-market cena* ir spēles nosaukums cenai, ko maksā datora (KI) tirgus.

## API kredīti

Katrs vaicājums, izņemot kredītu pārbaudi, maksā vienu kredītu. Savācējs vaicā
tikai tik bieži, cik dati mainās, aptuveni **19 kredīti dienā**:

| Cik bieži | Vaicājumi |
|---|---|
| ik 6 h | noliktava, tirgus, misijas |
| reizi dienā | spēlētājs, rūpnīcas, spec. ēkas, nauda, tirdzniecības žurnāls |
| reizi nedēļā | receptes, uzlabojumu izmaksas, pārstrāde, karaspēks, HQ, sasniegumi |
| pēc vajadzības | raktuves: kad prognozētais stāvoklis sasniedz pārbaudes līmeni (+ reizi nedēļā) |
| pēc vajadzības | preču saraksts: kad parādās nezināma prece (+ reizi mēnesī) |

Drošības ierobežojumi: dienas kredītu budžets, apstāšanās zem minimālā kredītu
skaita, un nekādu automātisku atkārtojumu. Pārskats tērē kredītus tikai ar pogu
"Atjaunot noliktavu" (ne biežāk kā reizi 5 minūtēs).

## Uzstādīšana

Vajag Python 3.10+ un API atslēgu no spēles.

```bash
git clone <šī repozitorija adrese>
cd resources-tool
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # ieraksti .env failā API atslēgu (un Telegram botu)
```

Telegram nav obligāts: bez tokena ziņas tiek izdrukātas terminālī.
Telegram ziņu valodu izvēlas ar `UI_LANG=lv` failā `.env`.

## Lietošana

```bash
python collector.py --status       # kas jāielādē, izlietotie kredīti (0 kredītu)
python collector.py --once         # ielādē to, kas jāielādē tagad
python collector.py                # strādā pastāvīgi (atstāj logu atvērtu)
python collector.py --fetch 2      # ielādē vienu vaicājumu tagad (1 kredīts)
python collector.py --report       # nosūta dienas atskaiti tagad (0 kredītu)

python -m web.app                  # pārskats adresē http://127.0.0.1:8050
```

## Drošība

- `.env` (API atslēga, Telegram tokens), datubāze un lejupielādētie paraugi ir
  `.gitignore` sarakstā. **Nekad tos nepublicē.** Datubāzē ir tava spēles vēsture.
- Pēc noklusējuma pārskats klausās tikai `127.0.0.1` (šajā datorā).
- `python -m web.app --lan` padara to pieejamu telefonā tajā pašā Wi-Fi tīklā.
  Pieslēgšanās nav, tāpēc lieto to tikai uzticamā tīklā. LAN režīmā poga, kas
  tērē kredītus, strādā tikai pašā datorā, ja vien nepievieno `--lan-refresh`.
- Atjaunošanas pieprasījumam vajag īpašu galveni, tāpēc citas vietnes nevar
  likt tavam pārlūkam tērēt kredītus.
- Kļūdu ziņās nekad nav API atslēgas.

## Atrastās spēles formulas

Izmērītas spēlē un pārbaudītas ar reālām uzlabojumu izmaksām:

- Noliktavas ietilpība = **5000 × līmenis²**
- Rūpnīcas ražība stundā = **līmenis × bāzes ražība**
- Rūpnīcas un spec. ēkas uzlabojuma cena = **bāzes cena × (mērķa līmenis)²**, arī preces
- Pārstrādes iznākums = **API bāzes daudzums × Recycling Plant līmenis**
- Raktuvju stāvoklis krītas par **~3,5–4 % dienā** (precizējas automātiski)
- Pērkot tirgū, nāk klāt **~9 % transports** (maksā pircējs)
- API nav unikāla raktuves ID: `mineID` ir raktuves *tips*, tāpēc raktuves atšķir pēc koordinātām

## Projekta struktūra

```
collector.py          grafiks, ielāde, brīdinājumu sūtīšana
probe.py              atsevišķu vaicājumu ielāde struktūras apskatei
rgtool/api.py         API klients (bez atkārtojumiem: tie maksā kredītus)
rgtool/schema.sql     datubāzes shēma (atsauces / stāvoklis / vēsture)
rgtool/db.py          saglabā katru API atbildi
rgtool/maintenance.py raktuvju stāvokļa prognoze
rgtool/alerts.py      brīdinājumi un dienas atskaite
rgtool/i18n.py        Telegram teksti (en, lv)
web/data.py           pārskata aprēķini (ražošanas modelis, atmaksāšanās)
web/app.py            Flask serveris
web/static/           lapa (JavaScript, Leaflet karte, SVG grafiki, i18n.js)
```

## Licence

MIT, skatīt [LICENSE](LICENSE).
