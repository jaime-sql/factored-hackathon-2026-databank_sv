# Data quality report — Factored AI & Data Hackathon 2026 (LATAM bank dataset)

Generated 2026-09-29 17:32 CST by `profile.py` (DuckDB 1.5.6). Source: local /workspace/hackathon-data/raw. Every number below is computed by the script.

## 1. Inventory

12505 objects, 10,081.1 MB total.

| table / prefix | files | MB | formats | rows loaded | dictionary rows | diff vs dict |
|---|---|---|---|---|---|---|
| branches | 1 | 0.09 | csv×1 | 350 | 350 | +0 |
| call_center_interactions | 1,097 | 139.7 | csv×1097 | 686,296 | 800,000 | -113,704 |
| call_transcripts | 1,097 | 137.2 | csv×1097 | 171,321 | 200,000 | -28,679 |
| campaign_sends | 1,083 | 326 | csv×1083 | 1,746,801 | 2,000,000 | -253,199 |
| complaints | 1,097 | 17.99 | csv×1097 | 67,095 | 80,000 | -12,905 |
| customers | 1 | 46.9 | csv×1 | 150,000 | 150,000 | +0 |
| daily_exchange_rates | 1 | 0.78 | csv×1 | 13,164 | 3,000 | +10,164 |
| data_backup_20260831 | 4,833 | 4,732 | csv×4833 | - | - | - |
| digital_events | 1,097 | 3,757 | csv×1097 | 15,620,994 | 10,000,000 | +5,620,994 |
| marketing_campaigns | 2 | 0.07 | csv×2 | 200 | 200 | +0 |
| products | 1 | 68.21 | csv×1 | 400,000 | 400,000 | +0 |
| satisfaction_surveys | 1,097 | 46.45 | csv×1097 | 212,759 | 250,000 | -37,241 |
| service_agents | 1 | 0.24 | csv×1 | 1,200 | 1,200 | +0 |
| transactions | 1,097 | 808.3 | csv×1097 | 4,425,008 | 5,000,000 | -574,992 |

Full object list: `inventory.tsv`.

## 2. Per-table profile

### branches

Rows **350** from 1 file(s). PK `branch_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns ['opening_time', 'closing_time'] (year/month/day = hive partition cols); inferred-type differences none.

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| branch_id | VARCHAR | 0.00% | 0 | ~416 |  |  |
| branch_code | VARCHAR | 0.00% | 0 | ~342 |  |  |
| branch_name | VARCHAR | 0.00% | 0 | ~171 |  |  |
| branch_type | VARCHAR | 0.00% | 0 | 4 |  | Express=130; Corporate=129; Premium=48; Main=43 |
| address | VARCHAR | 0.00% | 0 | ~318 | PII |  |
| city | VARCHAR | 0.00% | 0 | 16 |  | Puebla=33; Guadalajara=30; Tijuana=29; Ciudad de México=2... |
| state | VARCHAR | 0.00% | 0 | 16 |  | Puebla=33; Jalisco=30; Baja California=29; Ciudad de Méxi... |
| country | VARCHAR | 0.00% | 0 | 3 |  | México=175; Colombia=105; Argentina=70 |
| postal_code | VARCHAR | 0.00% | 0 | ~107 | PII |  |
| geographic_zone | VARCHAR | 0.00% | 0 | 1 |  | Urbana=350 |
| phone | VARCHAR | 0.00% | 0 | ~396 | PII |  |
| email | VARCHAR | 0.00% | 0 | ~361 | PII |  |
| opening_time | TIME | 0.00% |  | 4 |  | [08:00:00..09:30:00] 09:30:00=104; 09:00:00=89; 08:00:00=... |
| closing_time | TIME | 0.00% |  | 5 |  | [17:00:00..20:00:00] 17:00:00=91; 19:00:00=76; 20:00:00=6... |
| has_atms | BOOLEAN | 0.00% |  | 1 |  | 1=350 |
| atm_count | BIGINT | 0.00% |  | 7 |  | [2..8] 8=54; 4=53; 7=52; 3=52; 6=49; 5=46; 2=44 |
| has_teller_windows | BOOLEAN | 0.00% |  | 1 |  | 1=350 |
| teller_window_count | BIGINT | 0.00% |  | 10 |  | [3..12] 12=48; 10=39; 7=38; 6=38; 8=36; 9=34; 11=32; 3=30 |
| latitude | DOUBLE | 0.00% |  | ~348 | PII | min -34.69 / max 25.78 |
| longitude | DOUBLE | 0.00% |  | ~310 | PII | min -103.4 / max 0.1 |
| branch_opening_date | DATE | 0.00% |  | ~295 |  | min 1990-01-03 / max 2023-05-11 |
| branch_status | VARCHAR | 0.00% | 0 | 2 |  | Active=336; Temporarily Closed=14 |

### call_center_interactions

Rows **686,296** from 1097 file(s). PK `interaction_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences ['duration_seconds (dict INTEGER, file DOUBLE)', 'wait_time_seconds (dict INTEGER, file DOUBLE)'].

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| interaction_id | VARCHAR | 0.00% | 0 | ~715,842 |  |  |
| interaction_date | TIMESTAMP | 0.00% |  | ~896,070 |  | min 2023-06-17 08:03:26 / max 2026-06-18 07:58:13 |
| process_date | DATE | 0.00% |  | ~954 |  | min 2023-06-17 / max 2026-06-17 |
| customer_id | VARCHAR | 0.00% | 0 | ~164,963 |  |  |
| agent_id | VARCHAR | 0.00% | 0 | ~1,052 |  |  |
| interaction_type | VARCHAR | 0.00% | 0 | 5 |  | Inbound Call=480,678; Outbound Call=102,572; Chat=68,691;... |
| channel | VARCHAR | 0.00% | 0 | 6 |  | Phone=583,250; Email=27,543; App=26,364; WhatsApp=22,888;... |
| contact_reason | VARCHAR | 0.00% | 0 | 6 |  | Transaccional=240,056; Producto=150,863; Queja=117,021; T... |
| reason_category | VARCHAR | 0.00% | 0 | 6 |  | Transaccional=240,056; Producto=150,863; Queja=117,021; T... |
| duration_seconds | DOUBLE | 14.02% |  | ~1,124 |  | min 30 / max 1,204 |
| wait_time_seconds | DOUBLE | 29.96% |  | ~383 |  | min 0 / max 424 |
| was_resolved | BOOLEAN | 0.00% |  | 2 |  | 1=526,030; 0=160,266 |
| requires_followup | BOOLEAN | 0.00% |  | 2 |  | 0=447,242; 1=239,054 |
| detected_sentiment | VARCHAR | 0.00% | 0 | 5 |  | Neutral=459,712; Negativo=94,322; Positivo=75,562; Muy Ne... |
| sentiment_score | DOUBLE | 0.00% |  | ~188 |  | min -1 / max 1 |
| customer_detected_accent | VARCHAR | 29.83% | 0 | 3 |  | mexican=240,674; None=204,750; colombian=144,712; argenti... |
| agent_used_accent | VARCHAR | 29.83% | 0 | 3 |  | mexican=241,931; None=204,750; colombian=144,386; argenti... |
| was_escalated | BOOLEAN | 0.00% |  | 2 |  | 0=617,910; 1=68,386 |
| mentioned_products | VARCHAR | 60.03% | 0 | ~312,189 |  |  |
| has_transcript | BOOLEAN | 0.00% |  | 2 |  | 0=514,975; 1=171,321 |
| has_recording | BOOLEAN | 0.00% |  | 2 |  | 1=590,062; 0=96,234 |
| day | VARCHAR | 0.00% | 0 | 31 |  | 05=23,949; 11=23,764; 26=23,508; 20=23,464; 27=23,421; 18... |
| month | VARCHAR | 0.00% | 0 | 12 |  | 03=58,910; 07=58,662; 08=58,532; 12=57,935; 04=57,837; 10... |
| year | BIGINT | 0.00% |  | 4 |  | [2,023..2,026] 2,025=229,056; 2,024=228,210; 2,023=123,54... |

### call_transcripts

Rows **171,321** from 1097 file(s). PK `transcript_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences ['duration_seconds (dict INTEGER, file DOUBLE)'].

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| transcript_id | VARCHAR | 0.00% | 0 | ~180,126 |  |  |
| interaction_id | VARCHAR | 0.00% | 0 | ~208,322 |  |  |
| process_date | DATE | 0.00% |  | ~954 |  | min 2023-06-17 / max 2026-06-17 |
| customer_id | VARCHAR | 0.00% | 0 | ~103,670 |  |  |
| agent_id | VARCHAR | 0.00% | 0 | ~1,052 |  |  |
| full_text | VARCHAR | 0.00% | 0 | ~561 | PII |  |
| customer_text | VARCHAR | 0.00% | 0 | 42 | PII | Buenas tardes, necesito consultar el saldo de mi tarjeta ... |
| agent_text | VARCHAR | 0.00% | 0 | 42 | PII | Buenas tardes, claro que sí. Déjeme revisar esa informaci... |
| detected_language | VARCHAR | 0.00% | 0 | 1 |  | es=171,321 |
| detected_accent | VARCHAR | 36.82% | 0 | 3 |  | None=63,083; mexican=54,152; colombian=32,284; argentine=... |
| accent_confidence | DOUBLE | 10.01% |  | 25 |  | [0.75..0.99] None=17,141; 0.83=6,586; 0.85=6,568; 0.97=6,... |
| detected_keywords | VARCHAR | 5.13% | 0 | 12 |  | banco, servicio, cuenta=18,173; cuenta, servicio, banco=1... |
| mentioned_entities | VARCHAR | 10.02% | 0 | ~54 | PII |  |
| detected_intents | VARCHAR | 4.94% | 0 | 1 |  | consulta_general=162,864; None=8,457 |
| main_topics | VARCHAR | 0.00% | 0 | 6 |  | Transaccional=59,786; Producto=37,658; Queja=29,198; Técn... |
| transcription_model | VARCHAR | 0.00% | 0 | 4 |  | AWS Transcribe=43,117; Whisper v3=42,803; Google STT=42,7... |
| audio_quality | VARCHAR | 5.04% | 0 | 3 |  | High=114,371; Medium=40,350; None=8,638; Low=7,962 |
| duration_seconds | DOUBLE | 14.03% |  | ~1,063 |  | min 30 / max 1,151 |
| day | VARCHAR | 0.00% | 0 | 31 |  | 05=5,983; 26=5,958; 11=5,927; 20=5,901; 18=5,803; 27=5,79... |
| month | VARCHAR | 0.00% | 0 | 12 |  | 07=14,828; 03=14,824; 12=14,564; 08=14,564; 04=14,428; 10... |
| year | BIGINT | 0.00% |  | 4 |  | [2,023..2,026] 2,024=56,982; 2,025=56,974; 2,023=30,813; ... |

### campaign_sends

Rows **1,746,801** from 1083 file(s). PK `send_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences ['click_count (dict INTEGER, file DOUBLE)'].

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| send_id | VARCHAR | 0.00% | 0 | ~2,203,531 |  |  |
| send_date | TIMESTAMP | 0.00% |  | ~2,269,717 |  | min 2023-07-01 06:00:42 / max 2026-06-18 05:59:53 |
| process_date | DATE | 0.00% |  | ~954 |  | min 2023-07-01 / max 2026-06-17 |
| campaign_id | VARCHAR | 0.00% | 0 | ~164 |  |  |
| customer_id | VARCHAR | 0.00% | 0 | ~173,849 |  |  |
| send_channel | VARCHAR | 0.00% | 0 | 5 |  | Email=620,195; SMS=432,283; WhatsApp=349,144; Push=290,65... |
| template_used | VARCHAR | 10.03% | 0 | ~858 |  |  |
| subject | VARCHAR | 68.03% | 0 | 8 |  | None=1,188,342; ¡Oferta especial en Tarjeta Crédito!=191,... |
| send_status | VARCHAR | 0.00% | 0 | 4 |  | Sent=1,642,044; Failed=52,306; Bounced=34,900; Blocked=17... |
| was_delivered | BOOLEAN | 0.00% |  | 2 |  | 1=1,642,044; 0=104,757 |
| was_opened | BOOLEAN | 27.72% |  | 2 |  | 0=775,263; 1=487,309; None=484,229 |
| open_date | TIMESTAMP | 72.10% |  | ~486,253 |  | min 2023-07-01 07:44:22 / max 2026-06-25 03:30:02 |
| was_clicked | BOOLEAN | 0.00% |  | 2 |  | 0=1,649,008; 1=97,793 |
| click_date | TIMESTAMP | 94.40% |  | ~93,907 |  | min 2023-07-01 21:57:26 / max 2026-06-24 23:51:59 |
| click_count | DOUBLE | 94.40% |  | 5 |  | [1..5] None=1,649,008; 4=19,649; 1=19,593; 3=19,564; 5=19... |
| had_conversion | BOOLEAN | 0.00% |  | 2 |  | 0=1,737,002; 1=9,799 |
| conversion_date | TIMESTAMP | 99.44% |  | ~13,059 |  | min 2023-07-03 12:56:27 / max 2026-06-26 08:26:49 |
| conversion_value | DOUBLE | 99.44% |  | ~10,595 |  | min 100.9 / max 5,000 |
| open_device | VARCHAR | 74.90% | 0 | 3 |  | None=1,308,424; Desktop=146,494; Tablet=146,450; Mobile=1... |
| open_country | VARCHAR | 74.90% | 0 | 3 |  | None=1,308,278; México=219,090; Colombia=132,441; Argenti... |
| failure_reason | VARCHAR | 94.30% | 0 | 3 |  | None=1,647,204; SMTP error=49,706; Invalid email address=... |
| send_cost | DOUBLE | 15.00% |  | ~2,691 |  | min 0.0001 / max 0.3 |
| day | VARCHAR | 0.00% | 0 | 31 |  | 11=60,720; 02=60,467; 05=59,911; 08=59,848; 04=59,836; 10... |
| month | VARCHAR | 0.00% | 0 | 12 |  | 01=151,972; 12=150,716; 07=150,532; 08=150,473; 10=150,43... |
| year | BIGINT | 0.00% |  | 4 |  | [2,023..2,026] 2,024=591,104; 2,025=588,009; 2,023=295,36... |

### complaints

Rows **67,095** from 1097 file(s). PK `complaint_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences ['resolution_days (dict INTEGER, file DOUBLE)', 'resolution_satisfaction (dict INTEGER, file DOUBLE)'].

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| complaint_id | VARCHAR | 0.00% | 0 | ~66,008 |  |  |
| creation_date | TIMESTAMP | 0.00% |  | ~81,223 |  | min 2023-06-17 08:07:05 / max 2026-06-18 07:56:52 |
| process_date | DATE | 0.00% |  | ~954 |  | min 2023-06-17 / max 2026-06-17 |
| customer_id | VARCHAR | 0.00% | 0 | ~59,121 |  |  |
| case_type | VARCHAR | 0.00% | 0 | 4 |  | Complaint=40,452; Claim=16,598; Request=6,761; Suggestion... |
| category | VARCHAR | 0.00% | 0 | 5 |  | Transactions=13,580; Fees=13,553; Technical=13,407; Branc... |
| subcategory | VARCHAR | 9.98% | 0 | 5 |  | Cargo no reconocido=12,297; Cobro indebido=12,194; Proble... |
| reception_channel | VARCHAR | 0.00% | 0 | 6 |  | Call Center=33,761; Email=13,323; Web=9,884; App=6,727; B... |
| affected_product_id | VARCHAR | 33.57% | 0 | ~44,958 |  |  |
| related_branch_id | VARCHAR | 71.42% | 0 | ~416 |  |  |
| origin_interaction_id | VARCHAR | 100.00% | 0 | 0 |  | None=67,095 |
| description | VARCHAR | 0.00% | 0 | 5 | PII | Queja relacionada con transactions=13,580; Queja relacion... |
| claimed_amount | DOUBLE | 67.58% |  | ~19,506 |  | min 50.27 / max 5,000 |
| currency | VARCHAR | 67.54% | 0 | 4 |  | None=45,319; MXN=5,487; COP=5,456; USD=5,431; ARS=5,402 |
| priority | VARCHAR | 0.00% | 0 | 4 |  | Medium=33,439; Low=20,411; High=9,890; Critical=3,355 |
| status | VARCHAR | 0.00% | 0 | 6 |  | In Process=26,823; Open=20,125; Resolved=13,512; Escalate... |
| assigned_agent_id | VARCHAR | 34.45% | 0 | ~1,094 |  |  |
| assignment_date | TIMESTAMP | 34.47% |  | ~43,313 |  | min 2023-06-17 22:26:12 / max 2026-06-19 03:56:52 |
| first_response_date | TIMESTAMP | 39.11% |  | ~48,628 |  | min 2023-06-18 03:37:40 / max 2026-06-20 22:42:19 |
| resolution_date | TIMESTAMP | 77.12% |  | ~15,194 |  | min 2023-06-20 07:10:42 / max 2026-07-18 06:07:57 |
| closing_date | TIMESTAMP | 96.30% |  | ~2,006 |  | min 2023-06-26 11:38:44 / max 2026-07-18 22:15:16 |
| sla_breached | BOOLEAN | 0.00% |  | 2 |  | 0=53,600; 1=13,495 |
| resolution_days | DOUBLE | 77.10% |  | 30 |  | [1..30] None=51,732; 9=551; 25=547; 30=539; 24=539; 28=53... |
| resolution | VARCHAR | 77.18% | 0 | 5 | PII | None=51,785; Se revisó el caso y se realizó el ajuste cor... |
| compensation_granted | DOUBLE | 93.08% |  | ~3,311 |  | min 10.15 / max 500 |
| resolution_satisfaction | DOUBLE | 96.30% |  | 5 |  | [1..5] None=64,611; 5=526; 3=514; 1=500; 2=472; 4=472 |
| is_repeat_complainer | BOOLEAN | 0.00% |  | 2 |  | 0=57,009; 1=10,086 |
| day | VARCHAR | 0.00% | 0 | 31 |  | 11=2,334; 20=2,322; 10=2,309; 26=2,276; 27=2,266; 05=2,26... |
| month | VARCHAR | 0.00% | 0 | 12 |  | 01=5,820; 12=5,774; 07=5,762; 10=5,730; 08=5,672; 03=5,65... |
| year | BIGINT | 0.00% |  | 4 |  | [2,023..2,026] 2,025=22,356; 2,024=22,329; 2,023=12,078; ... |

### customers

Rows **150,000** from 1 file(s). PK `customer_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences ['credit_score (dict INTEGER, file DOUBLE)'].

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| customer_id | VARCHAR | 0.00% | 0 | ~173,849 |  |  |
| document_number | VARCHAR | 0.00% | 0 | ~165,394 | PII |  |
| document_type | VARCHAR | 0.00% | 0 | 4 | PII | DNI=104,749; CE=15,150; Pasaporte=15,062; CC=15,039 |
| first_name | VARCHAR | 0.00% | 0 | ~6,810 | PII |  |
| last_name | VARCHAR | 0.00% | 0 | ~4,365 | PII |  |
| date_of_birth | DATE | 0.00% |  | ~21,747 | PII | min 1942-07-07 / max 2005-06-21 |
| gender | VARCHAR | 0.00% | 0 | 3 |  | F=50,508; O=49,808; M=49,684 |
| email | VARCHAR | 1.99% | 0 | ~84,951 | PII |  |
| mobile_phone | VARCHAR | 3.14% | 0 | ~154,153 | PII |  |
| landline_phone | VARCHAR | 50.04% | 0 | ~54,920 | PII |  |
| address | VARCHAR | 4.91% | 0 | ~168,966 | PII |  |
| city | VARCHAR | 0.00% | 0 | 16 |  | Guadalajara=12,643; Ciudad de México=12,506; Querétaro=12... |
| state | VARCHAR | 0.00% | 0 | 16 |  | Jalisco=12,643; Ciudad de México=12,506; Querétaro=12,500... |
| country | VARCHAR | 0.00% | 0 | 3 |  | México=74,907; Colombia=45,251; Argentina=29,842 |
| postal_code | VARCHAR | 10.03% | 0 | ~7,594 | PII |  |
| detected_accent | VARCHAR | 29.88% | 0 | 3 |  | mexican=52,505; None=44,817; colombian=31,666; argentine=... |
| segment | VARCHAR | 0.00% | 0 | 4 |  | Basic=89,756; Plus=37,547; Premium=15,207; Student=7,490 |
| credit_score | DOUBLE | 14.99% |  | ~369 |  | min 422 / max 850 |
| estimated_monthly_income | DOUBLE | 20.02% |  | ~120,121 |  | min 5,100 / max 111,895,075 |
| occupation | VARCHAR | 10.03% | 0 | 20 |  | None=15,039; Manager=6,862; Accountant=6,857; Salesperson... |
| marital_status | VARCHAR | 7.97% | 0 | 4 |  | Married=34,765; Divorced=34,734; Single=34,474; Widowed=3... |
| education_level | VARCHAR | 11.97% | 0 | 5 |  | College Prep=39,583; High School=33,120; University=32,87... |
| registration_date | TIMESTAMP | 0.00% |  | ~184,855 |  | min 2018-06-18 01:21:11 / max 2026-06-17 23:53:29 |
| registration_branch_id | VARCHAR | 0.00% | 0 | ~129,978 |  |  |
| customer_status | VARCHAR | 0.00% | 0 | 4 |  | Active=127,700; Inactive=14,914; Suspended=4,407; Closed=... |
| last_updated | TIMESTAMP | 0.00% |  | ~151,485 |  | min 2018-06-18 15:09:31 / max 2027-06-15 19:35:27 |
| accepts_marketing | BOOLEAN | 0.00% |  | 2 |  | 0=75,007; 1=74,993 |

### daily_exchange_rates

Rows **13,164** from 1 file(s). PK `date,source_currency,target_currency`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences none.

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| date | DATE | 0.00% |  | ~954 |  | min 2023-06-17 / max 2026-06-17 |
| source_currency | VARCHAR | 0.00% | 0 | 4 |  | MXN=3,291; ARS=3,291; USD=3,291; COP=3,291 |
| target_currency | VARCHAR | 0.00% | 0 | 4 |  | MXN=3,291; ARS=3,291; USD=3,291; COP=3,291 |
| exchange_rate | DOUBLE | 0.00% |  | ~8,255 |  | min 0.000245 / max 4,080 |
| buy_rate | DOUBLE | 0.00% |  | ~8,889 |  | min 0.000241 / max 4,058 |
| sell_rate | DOUBLE | 0.00% |  | ~8,945 |  | min 0.000246 / max 4,139 |
| source | VARCHAR | 0.00% | 0 | 4 |  | Bloomberg=3,303; Reuters=3,297; Internal=3,293; Central B... |

### digital_events

Rows **15,620,994** from 1097 file(s). PK `event_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences ['duration_seconds (dict INTEGER, file DOUBLE)'].

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| event_id | VARCHAR | 0.00% | 0 | ~14,709,111 |  |  |
| event_date | TIMESTAMP | 0.00% |  | ~15,208,045 |  | min 2023-06-17 06:02:03 / max 2026-06-18 06:04:05 |
| process_date | DATE | 0.00% |  | ~954 |  | min 2023-06-17 / max 2026-06-17 |
| customer_id | VARCHAR | 23.98% | 0 | ~173,849 |  |  |
| session_id | VARCHAR | 0.00% | 0 | ~1,837,582 |  |  |
| event_type | VARCHAR | 0.00% | 0 | 7 |  | PageView=5,972,564; Click=3,585,034; Login=2,434,770; Log... |
| event_category | VARCHAR | 0.00% | 0 | 4 |  | Authentication=4,868,382; Navigation=3,961,324; Product=3... |
| channel | VARCHAR | 0.00% | 0 | 4 |  | Android App=5,476,164; iOS App=3,899,497; Desktop Web=3,1... |
| platform | VARCHAR | 5.00% | 0 | 5 |  | Android=6,685,963; iOS=5,182,421; Windows=991,807; Linux=... |
| browser | VARCHAR | 62.02% | 0 | 5 |  | None=9,687,736; Safari=1,728,968; Chrome=1,725,978; Samsu... |
| app_version | VARCHAR | 42.98% | 0 | ~526 |  |  |
| page_url | VARCHAR | 5.00% | 0 | 12 |  | /login=2,312,677; /logout=2,312,586; /products/loans=1,19... |
| page_title | VARCHAR | 4.99% | 0 | 12 |  | Cerrar Sesión=2,312,841; Iniciar Sesión=2,312,796; Présta... |
| action | VARCHAR | 10.00% | 0 | 10 |  | view_product=3,407,643; logout=2,191,640; login=2,189,929... |
| element_id | VARCHAR | 15.00% | 0 | 12 |  | None=2,343,244; login_form=2,070,024; logout_btn=2,069,55... |
| product_id | VARCHAR | 90.78% | 0 | ~465,190 |  |  |
| event_value | DOUBLE | 94.91% |  | ~361,218 |  | min 10.01 / max 5,000 |
| duration_seconds | DOUBLE | 63.67% |  | ~306 |  | min 5 / max 300 |
| ip_address | VARCHAR | 5.00% | 0 | ~1,606,932 | PII |  |
| ip_country | VARCHAR | 0.00% | 0 | 4 |  | México=6,242,893; Colombia=4,806,882; Argentina=3,533,045... |
| ip_city | VARCHAR | 27.98% | 0 | 16 |  | None=4,370,476; Guadalajara=951,621; Querétaro=938,075; T... |
| is_mobile | BOOLEAN | 0.00% |  | 2 |  | 1=12,492,143; 0=3,128,851 |
| referrer | VARCHAR | 93.29% | 0 | 4 |  | None=14,573,469; https://www.instagram.com=262,214; https... |
| utm_source | VARCHAR | 94.63% | 0 | 4 |  | None=14,781,949; email=210,149; direct=209,721; google=20... |
| utm_medium | VARCHAR | 94.63% | 0 | 4 |  | None=14,781,860; organic=210,210; email=209,778; social=2... |
| utm_campaign | VARCHAR | 94.63% | 0 | 3 |  | None=14,782,077; retention=280,033; spring_promo=279,962;... |
| day | VARCHAR | 0.00% | 0 | 31 |  | 06=589,755; 18=568,732; 10=563,648; 11=557,557; 23=557,28... |
| month | VARCHAR | 0.00% | 0 | 12 |  | 01=1,456,469; 07=1,452,232; 05=1,366,212; 09=1,319,844; 0... |
| year | BIGINT | 0.00% |  | 4 |  | [2,023..2,026] 2,025=5,173,832; 2,024=5,057,968; 2,023=2,... |

### marketing_campaigns

Rows **200** from 1 file(s). PK `campaign_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences none.

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| campaign_id | VARCHAR | 0.00% | 0 | ~207 |  |  |
| campaign_name | VARCHAR | 0.00% | 0 | ~188 |  |  |
| description | VARCHAR | 19.50% | 0 | 37 | PII | None=39; Campaña de retention para Tarjeta Crédito=16; Ca... |
| campaign_type | VARCHAR | 0.00% | 0 | 6 |  | Email=67; SMS=42; WhatsApp=37; Push=24; Mix=21; Voice=9 |
| campaign_objective | VARCHAR | 0.00% | 0 | 5 |  | Retention=62; Cross-sell=51; Acquisition=38; Reactivation... |
| promoted_product | VARCHAR | 11.00% | 0 | 7 |  | Tarjeta Crédito=52; Cuenta Ahorro=40; Préstamo Personal=2... |
| target_segment | VARCHAR | 39.50% | 0 | 4 |  | None=79; Plus=32; Premium=32; Basic=30; Student=27 |
| target_country | VARCHAR | 55.50% | 0 | 3 |  | None=111; Colombia=33; Mexico=28; Argentina=28 |
| start_date | DATE | 0.00% |  | ~192 |  | min 2023-07-01 / max 2026-06-14 |
| end_date | DATE | 0.00% |  | ~179 |  | min 2023-08-11 / max 2026-08-20 |
| budget | DOUBLE | 15.50% |  | ~171 |  | min 6,355 / max 5e+05 |
| campaign_status | VARCHAR | 0.00% | 0 | 3 |  | Completed=172; Paused=25; Active=3 |
| expected_conversion_rate | DOUBLE | 7.00% |  | ~204 |  | min 0.55 / max 14.69 |

### products

Rows **400,000** from 1 file(s). PK `product_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences ['days_past_due (dict INTEGER, file DOUBLE)'].

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| product_id | VARCHAR | 0.00% | 0 | ~467,436 |  |  |
| customer_id | VARCHAR | 0.00% | 0 | ~172,609 |  |  |
| product_type | VARCHAR | 0.00% | 0 | 8 |  | Cuenta Ahorro=120,203; Tarjeta Crédito=100,102; Cuenta Co... |
| product_number | VARCHAR | 0.00% | 0 | ~424,581 | PII |  |
| currency | VARCHAR | 0.00% | 0 | 3 |  | USD=220,501; COP=107,975; ARS=71,524 |
| current_balance | DOUBLE | 0.00% |  | ~301,378 |  | min 0 / max 881,511,546 |
| credit_limit | DOUBLE | 68.67% |  | ~109,646 |  | min 1,000 / max 599,984,206 |
| interest_rate | DOUBLE | 10.02% |  | ~3,314 |  | min 0 / max 45 |
| opening_date | DATE | 0.00% |  | ~2,917 |  | min 2018-06-18 / max 2026-06-17 |
| expiration_date | DATE | 66.71% |  | ~4,657 |  | min 2021-06-17 / max 2031-06-16 |
| opening_branch_id | VARCHAR | 0.00% | 0 | ~416 |  |  |
| product_status | VARCHAR | 0.00% | 0 | 4 |  | Active=339,965; Closed=32,039; Blocked=19,935; Suspended=... |
| opening_channel | VARCHAR | 0.00% | 0 | 4 |  | Branch=199,838; Web=100,282; App=79,726; Call Center=20,154 |
| has_linked_app | BOOLEAN | 0.00% |  | 2 |  | 0=200,142; 1=199,858 |
| days_past_due | DOUBLE | 68.66% |  | 7 |  | [0..180] None=274,650; 0=106,585; 90=3,233; 30=3,117; 15=... |
| last_transaction_date | TIMESTAMP | 23.57% |  | ~267,083 |  | min 2018-06-21 17:07:15 / max 2026-06-17 23:17:43 |
| last_updated | TIMESTAMP | 0.00% |  | ~429,317 |  | min 2018-06-20 05:21:54 / max 2027-06-15 02:26:58 |

### satisfaction_surveys

Rows **212,759** from 1097 file(s). PK `survey_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns ['question_1_text', 'question_1_response', 'question_2_text', 'question_2_response', 'question_3_text', 'question_3_response'] (year/month/day = hive partition cols); inferred-type differences none.

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| survey_id | VARCHAR | 0.00% | 0 | ~202,151 |  |  |
| survey_date | TIMESTAMP | 0.00% |  | ~226,806 |  | min 2023-06-17 09:29:20 / max 2026-06-19 06:54:58 |
| process_date | DATE | 0.00% |  | ~954 |  | min 2023-06-17 / max 2026-06-17 |
| interaction_id | VARCHAR | 0.00% | 0 | ~245,496 |  |  |
| customer_id | VARCHAR | 0.00% | 0 | ~140,954 |  |  |
| agent_id | VARCHAR | 0.00% | 0 | ~1,052 |  |  |
| survey_type | VARCHAR | 0.00% | 0 | 3 |  | CSAT=127,856; NPS=63,668; CES=21,235 |
| send_channel | VARCHAR | 0.00% | 0 | 5 |  | Email=84,880; SMS=63,798; App=42,595; IVR=10,836; Web=10,650 |
| main_score | BIGINT | 0.00% |  | 7 |  | [1..7] 3=90,363; 2=46,398; 4=21,805; 5=16,475; 6=16,329; ... |
| nps_category | VARCHAR | 71.61% | 0 | 2 |  | None=152,365; Detractor=45,007; Passive=15,387 |
| question_1_text | VARCHAR | 42.99% | 0 | 3 |  | None=91,456; ¿Cómo calificaría la atención brindada?=40,6... |
| question_1_response | DOUBLE | 42.95% |  | 5 |  | [1..5] None=91,389; 5=24,575; 3=24,314; 2=24,217; 4=24,21... |
| question_2_text | VARCHAR | 61.75% | 0 | 1 |  | None=131,388; ¿El tiempo de espera fue aceptable?=81,371 |
| question_2_response | DOUBLE | 61.70% |  | 5 |  | [1..5] None=131,263; 3=16,567; 4=16,473; 2=16,217; 5=16,1... |
| question_3_text | VARCHAR | 81.13% | 0 | 1 |  | None=172,615; ¿Volvería a contactarnos por este canal?=40... |
| question_3_response | DOUBLE | 81.15% |  | 5 |  | [1..5] None=172,656; 1=8,176; 4=8,097; 3=8,030; 2=7,954; ... |
| open_comments | VARCHAR | 52.44% | 0 | 13 | PII | None=111,563; Tardaron mucho en atenderme.=13,620; No res... |
| comment_sentiment | VARCHAR | 52.41% | 0 | 3 |  | None=111,502; Negative=67,529; Neutral=26,774; Positive=6... |
| response_time_hours | DOUBLE | 0.00% |  | ~2,393 |  | min 1.01 / max 35.97 |
| campaign_response_rate | DOUBLE | 15.06% |  | ~2,452 |  | min 15 / max 45 |
| day | VARCHAR | 0.00% | 0 | 31 |  | 05=7,425; 11=7,368; 26=7,289; 20=7,272; 27=7,261; 18=7,17... |
| month | VARCHAR | 0.00% | 0 | 12 |  | 03=18,261; 07=18,185; 08=18,147; 12=17,965; 04=17,930; 10... |
| year | BIGINT | 0.00% |  | 4 |  | [2,023..2,026] 2,025=71,004; 2,024=70,753; 2,023=38,302; ... |

### service_agents

Rows **1,200** from 1 file(s). PK `agent_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences ['total_monthly_interactions (dict INTEGER, file DOUBLE)'].

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| agent_id | VARCHAR | 0.00% | 0 | ~1,094 |  |  |
| employee_code | VARCHAR | 0.00% | 0 | ~1,492 | PII |  |
| first_name | VARCHAR | 0.00% | 0 | ~401 | PII |  |
| last_name | VARCHAR | 0.00% | 0 | ~1,107 | PII |  |
| email | VARCHAR | 0.00% | 0 | ~1,312 | PII |  |
| phone | VARCHAR | 5.75% | 0 | ~1,341 | PII |  |
| native_accent | VARCHAR | 0.00% | 0 | 3 |  | mexican=600; colombian=360; argentine=240 |
| country_of_origin | VARCHAR | 0.00% | 0 | 3 |  | Mexico=600; Colombia=360; Argentina=240 |
| assigned_branch_id | VARCHAR | 30.58% | 0 | ~765 |  |  |
| agent_type | VARCHAR | 0.00% | 0 | 4 |  | Phone=588; Digital=251; In-Person=230; Hybrid=131 |
| experience_level | VARCHAR | 0.00% | 0 | 4 |  | Specialist=761; Senior=286; Mid-Senior=135; Junior=18 |
| languages | VARCHAR | 0.00% | 0 | 4 |  | español=649; español, inglés=422; español, portugués=68; ... |
| specialty | VARCHAR | 39.67% | 0 | 8 |  | None=476; Fraudes=105; Cobranza=97; Retención=96; Soporte... |
| hire_date | DATE | 0.00% |  | ~898 |  | min 2013-06-20 / max 2026-03-17 |
| avg_csat | DOUBLE | 11.17% |  | ~163 |  | min 3.5 / max 5 |
| total_monthly_interactions | DOUBLE | 9.25% |  | ~595 |  | min 100 / max 800 |
| agent_status | VARCHAR | 0.00% | 0 | 4 |  | Active=1,090; Vacation=62; Leave=29; Inactive=19 |
| work_shift | VARCHAR | 0.00% | 0 | 4 |  | Afternoon=418; Morning=398; Rotating=203; Night=181 |

### transactions

Rows **4,425,008** from 1097 file(s). PK `transaction_id`: 0 null, 0 duplicate rows over 0 keys (0.00%). Fully duplicated rows: 0 (0.00%).

Vs dictionary: missing columns none; extra columns none (year/month/day = hive partition cols); inferred-type differences none.

| column | type | null % | empty str | distinct | PII | top values / range |
|---|---|---|---|---|---|---|
| transaction_id | VARCHAR | 0.00% | 0 | ~4,394,559 |  |  |
| transaction_date | TIMESTAMP | 0.00% |  | ~3,855,236 |  | min 2023-06-17 06:01:30 / max 2026-06-18 05:59:41 |
| process_date | DATE | 0.00% |  | ~954 |  | min 2023-06-17 / max 2026-06-17 |
| product_id | VARCHAR | 0.00% | 0 | ~405,731 |  |  |
| customer_id | VARCHAR | 0.00% | 0 | ~167,822 |  |  |
| transaction_type | VARCHAR | 0.00% | 0 | 6 |  | Purchase=1,083,406; Withdrawal=964,673; Transfer=896,438;... |
| transaction_category | VARCHAR | 60.87% | 0 | 6 |  | None=2,693,520; Food=432,468; Services=345,370; Other=260... |
| amount | DOUBLE | 0.00% |  | ~3,608,253 |  | min 5 / max 39,999,828 |
| currency | VARCHAR | 0.00% | 0 | 3 |  | USD=2,437,979; COP=1,194,444; ARS=792,585 |
| amount_usd | DOUBLE | 57.34% |  | ~465,399 |  | min 5 / max 1e+04 |
| channel | VARCHAR | 0.00% | 0 | 6 |  | POS=1,548,161; ATM=1,328,334; Web=663,445; App=663,414; B... |
| branch_id | VARCHAR | 68.63% | 0 | ~416 |  |  |
| merchant_name | VARCHAR | 76.74% | 0 | 24 |  | None=3,395,774; Super Ahorro=64,527; Restaurante El Buen ... |
| merchant_category | VARCHAR | 76.75% | 0 | 6 |  | None=3,396,215; Food=256,846; Services=205,124; Other=155... |
| transaction_country | VARCHAR | 0.00% | 0 | 7 |  | México=2,105,794; Colombia=1,289,503; Argentina=867,561; ... |
| transaction_city | VARCHAR | 10.00% | 0 | 28 |  | None=442,611; Guadalajara=325,400; Monterrey=324,589; Pue... |
| transaction_status | VARCHAR | 0.00% | 0 | 4 |  | Approved=4,070,681; Declined=221,234; Pending=88,343; Rev... |
| response_code | VARCHAR | 5.00% | 0 | 5 |  | 00=3,867,312; None=221,033; 14=84,472; 51=84,179; 05=84,1... |
| is_fraud | BOOLEAN | 0.00% |  | 2 |  | 0=4,420,692; 1=4,316 |
| fraud_score | DOUBLE | 20.00% |  | ~4,340 |  | min 0 / max 99.99 |
| latitude | DOUBLE | 80.63% |  | ~896,975 | PII | min -35.6 / max 5.711 |
| longitude | DOUBLE | 80.63% |  | ~1,013,797 | PII | min -75.07 / max 1 |
| day | VARCHAR | 0.00% | 0 | 31 |  | 12=152,229; 17=151,070; 13=150,409; 25=149,983; 11=149,90... |
| month | VARCHAR | 0.00% | 0 | 12 |  | 10=385,079; 05=380,250; 07=377,304; 08=375,914; 12=371,65... |
| year | BIGINT | 0.00% |  | 4 |  | [2,023..2,026] 2,024=1,471,814; 2,025=1,466,502; 2,023=80... |

## 2b. Differences vs data dictionary

- **branches**: missing -; extra ['opening_time', 'closing_time']; type -
- **call_center_interactions**: missing -; extra -; type ['duration_seconds (dict INTEGER, file DOUBLE)', 'wait_time_seconds (dict INTEGER, file DOUBLE)']
- **call_transcripts**: missing -; extra -; type ['duration_seconds (dict INTEGER, file DOUBLE)']
- **campaign_sends**: missing -; extra -; type ['click_count (dict INTEGER, file DOUBLE)']
- **complaints**: missing -; extra -; type ['resolution_days (dict INTEGER, file DOUBLE)', 'resolution_satisfaction (dict INTEGER, file DOUBLE)']
- **customers**: missing -; extra -; type ['credit_score (dict INTEGER, file DOUBLE)']
- **daily_exchange_rates**: columns match dictionary
- **digital_events**: missing -; extra -; type ['duration_seconds (dict INTEGER, file DOUBLE)']
- **marketing_campaigns**: columns match dictionary
- **products**: missing -; extra -; type ['days_past_due (dict INTEGER, file DOUBLE)']
- **satisfaction_surveys**: missing -; extra ['question_1_text', 'question_1_response', 'question_2_text', 'question_2_response', 'question_3_text', 'question_3_response']; type -
- **service_agents**: missing -; extra -; type ['total_monthly_interactions (dict INTEGER, file DOUBLE)']
- **transactions**: columns match dictionary
- **call_center_interactions** rows 686,296 vs dictionary 800,000 (-113,704)
- **call_transcripts** rows 171,321 vs dictionary 200,000 (-28,679)
- **campaign_sends** rows 1,746,801 vs dictionary 2,000,000 (-253,199)
- **complaints** rows 67,095 vs dictionary 80,000 (-12,905)
- **daily_exchange_rates** rows 13,164 vs dictionary 3,000 (+10,164)
- **digital_events** rows 15,620,994 vs dictionary 10,000,000 (+5,620,994)
- **satisfaction_surveys** rows 212,759 vs dictionary 250,000 (-37,241)
- **transactions** rows 4,425,008 vs dictionary 5,000,000 (-574,992)

## 3. PII columns

| table | column | detected by |
|---|---|---|
| branches | address | name match |
| branches | postal_code | name match |
| branches | phone | name match |
| branches | email | name match |
| branches | latitude | name match |
| branches | longitude | name match |
| call_transcripts | full_text | free text |
| call_transcripts | customer_text | free text |
| call_transcripts | agent_text | free text |
| call_transcripts | mentioned_entities | free text |
| complaints | description | free text |
| complaints | resolution | free text |
| customers | document_number | name match |
| customers | document_type | name match |
| customers | first_name | name match |
| customers | last_name | name match |
| customers | date_of_birth | name match |
| customers | email | name match |
| customers | mobile_phone | name match |
| customers | landline_phone | name match |
| customers | address | name match |
| customers | postal_code | name match |
| digital_events | ip_address | name match |
| marketing_campaigns | description | free text |
| products | product_number | name match |
| satisfaction_surveys | open_comments | free text |
| service_agents | employee_code | name match |
| service_agents | first_name | name match |
| service_agents | last_name | name match |
| service_agents | email | name match |
| service_agents | phone | name match |
| transactions | latitude | name match |
| transactions | longitude | name match |

## 4. Data issues (computed)

- **call_center_interactions**: nulls ≥5%: duration_seconds 14.0%, wait_time_seconds 30.0%, customer_detected_accent 29.8%, agent_used_accent 29.8%, mentioned_products 60.0%; row count 686,296 vs dictionary 800,000
- **call_transcripts**: nulls ≥5%: detected_accent 36.8%, accent_confidence 10.0%, detected_keywords 5.1%, mentioned_entities 10.0%, audio_quality 5.0%, duration_seconds 14.0%; row count 171,321 vs dictionary 200,000
- **campaign_sends**: nulls ≥5%: template_used 10.0%, subject 68.0%, was_opened 27.7%, open_date 72.1%, click_date 94.4%, click_count 94.4%, conversion_date 99.4%, conversion_value 99.4%, open_device 74.9%, open_country 74.9%, failure_reason 94.3%, send_cost 15.0%; row count 1,746,801 vs dictionary 2,000,000
- **complaints**: nulls ≥5%: subcategory 10.0%, affected_product_id 33.6%, related_branch_id 71.4%, origin_interaction_id 100.0%, claimed_amount 67.6%, currency 67.5%, assigned_agent_id 34.5%, assignment_date 34.5%, first_response_date 39.1%, resolution_date 77.1%, closing_date 96.3%, resolution_days 77.1%, resolution 77.2%, compensation_granted 93.1%, resolution_satisfaction 96.3%; row count 67,095 vs dictionary 80,000
- **customers**: nulls ≥5%: landline_phone 50.0%, postal_code 10.0%, detected_accent 29.9%, credit_score 15.0%, estimated_monthly_income 20.0%, occupation 10.0%, marital_status 8.0%, education_level 12.0%
- **daily_exchange_rates**: row count 13,164 vs dictionary 3,000
- **digital_events**: nulls ≥5%: customer_id 24.0%, browser 62.0%, app_version 43.0%, action 10.0%, element_id 15.0%, product_id 90.8%, event_value 94.9%, duration_seconds 63.7%, ip_city 28.0%, referrer 93.3%, utm_source 94.6%, utm_medium 94.6%, utm_campaign 94.6%; row count 15,620,994 vs dictionary 10,000,000
- **marketing_campaigns**: nulls ≥5%: description 19.5%, promoted_product 11.0%, target_segment 39.5%, target_country 55.5%, budget 15.5%, expected_conversion_rate 7.0%
- **products**: nulls ≥5%: credit_limit 68.7%, interest_rate 10.0%, expiration_date 66.7%, days_past_due 68.7%, last_transaction_date 23.6%
- **satisfaction_surveys**: nulls ≥5%: nps_category 71.6%, question_1_text 43.0%, question_1_response 43.0%, question_2_text 61.8%, question_2_response 61.7%, question_3_text 81.1%, question_3_response 81.2%, open_comments 52.4%, comment_sentiment 52.4%, campaign_response_rate 15.1%; row count 212,759 vs dictionary 250,000
- **service_agents**: nulls ≥5%: phone 5.8%, assigned_branch_id 30.6%, specialty 39.7%, avg_csat 11.2%, total_monthly_interactions 9.2%
- **transactions**: nulls ≥5%: transaction_category 60.9%, amount_usd 57.3%, branch_id 68.6%, merchant_name 76.7%, merchant_category 76.8%, transaction_city 10.0%, fraud_score 20.0%, latitude 80.6%, longitude 80.6%; row count 4,425,008 vs dictionary 5,000,000
- **transactions**: process_date > transaction date on 0 rows (late arrivals, max lag 0 days); process_date < transaction date on 1,106,307 rows.
- transactions whose customer_id ≠ owner of product_id: 0
- complaints: resolution_date < creation_date 0; first_response < creation 0; closing < resolution 0; resolution_days inconsistent with dates (>1 day) 0.
- complaints with customer_id not in customers: 0

## 5. Dispute-workflow readiness

### a. Fraud score / label / status (transactions, PK-deduplicated: 4,425,008 rows)

- **transaction_status**: Approved=4,070,681 (91.99%); Declined=221,234 (5.00%); Pending=88,343 (2.00%); Reversed=44,750 (1.01%)
- **is_fraud**: 0=4,420,692 (99.90%); 1=4,316 (0.10%)
- **transaction_type**: Purchase=1,083,406 (24.48%); Withdrawal=964,673 (21.80%); Transfer=896,438 (20.26%); Payment=738,964 (16.70%); Deposit=609,409 (13.77%); Adjustment=132,118 (2.99%)
- **channel**: POS=1,548,161 (34.99%); ATM=1,328,334 (30.02%); Web=663,445 (14.99%); App=663,414 (14.99%); Branch=132,495 (2.99%); Transfer=89,159 (2.01%)
- **fraud_score**: non-null 3,539,851 (80.00%); min 0, max 99.99, mean 15.03, p50/p90/p99 [15.01, 27.02, 29.72]; out of [0,100]: 0
- fraud_score histogram (bucket=count): 0=1,179,452; 10=1,179,243; 20=1,178,174; 30=969; 40=343; 50=327; 60=344; 70=326; 80=334; 90=339
- fraud_score by is_fraud: False: n=4,420,692, mean=15, median=15; True: n=4,316, mean=49.46, median=48.93

| transaction_status | is_fraud | rows |
|---|---|---|
| Approved | 0 | 4,066,695 |
| Approved | 1 | 3,986 |
| Declined | 0 | 221,019 |
| Declined | 1 | 215 |
| Pending | 0 | 88,264 |
| Pending | 1 | 79 |
| Reversed | 0 | 44,714 |
| Reversed | 1 | 36 |

- transaction_date range: 2023-06-17 06:01:30 → 2026-06-18 05:59:41

### b. Duplicate-charge candidates

Base: 1,029,234 PK-unique transactions with a merchant_name. A candidate = a transaction whose previous transaction with the same (customer_id, merchant_name, amount) is within the window.

| window | candidates | % of base |
|---|---|---|
| 0s (identical ts) | 0 | 0.00% |
| <=10 min | 0 | 0.00% |
| <=1 h | 0 | 0.00% |
| <=24 h | 0 | 0.00% |

<=10 min candidates by status: 

Raw table rows sharing (customer, merchant, amount, timestamp) with another row: 0 (includes ingestion duplicates).

### c. Complaint → transaction linkage

Complaints (PK-dedup): 67,095; affected_product_id null: 22,525; orphan product: 0; product owner ≠ complaint customer: 44,570.
There is no transaction_id on complaints. Join path: `complaints.affected_product_id = transactions.product_id AND complaints.customer_id = transactions.customer_id AND transaction_date in [creation_date - window, creation_date)`. Secondary path: `complaints.origin_interaction_id → call_center_interactions.mentioned_products`.

Affected product type: None=22,525; Cuenta Ahorro=13,517; Cuenta Corriente=11,224; Tarjeta Crédito=11,064; Tarjeta Débito=4,422; Préstamo Personal=2,169; Préstamo Hipotecario=1,324; Inversión=633; Seguro=217

Dispute definition: category = 'Transactions' (subcategory 'Cargo no reconocido' or null); broad = Transactions + Fees. Transactions complaints: **13,580**; Transactions+Fees: **27,133**.

| complaints | candidate window | n | 0 tx | exactly 1 | 2–5 | >5 |
|---|---|---|---|---|---|---|
| all | n1 | 67,095 | 100.00% | 0.00% | 0.00% | 0.00% |
| all | n7 | 67,095 | 100.00% | 0.00% | 0.00% | 0.00% |
| all | n30 | 67,095 | 100.00% | 0.00% | 0.00% | 0.00% |
| all | n30_pendrev | 67,095 | 100.00% | 0.00% | 0.00% | 0.00% |
| all | n30_fraud | 67,095 | 100.00% | 0.00% | 0.00% | 0.00% |
| all w/ claimed_amount | n30 | 21,751 | 100.00% | 0.00% | 0.00% | 0.00% |
| all w/ claimed_amount | n30_amt | 21,751 | 100.00% | 0.00% | 0.00% | 0.00% |
| all w/ claimed_amount | n30_amtcur | 21,751 | 100.00% | 0.00% | 0.00% | 0.00% |
| all w/ claimed_amount | n30_amt1pct | 21,751 | 100.00% | 0.00% | 0.00% | 0.00% |
| all | n30 customer-any-product | 67,095 | 50.72% | 28.63% | 20.41% | 0.24% |
| Transactions | n1 | 13,580 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions | n7 | 13,580 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions | n30 | 13,580 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions | n30_pendrev | 13,580 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions | n30_fraud | 13,580 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions w/ claimed_amount | n30 | 4,500 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions w/ claimed_amount | n30_amt | 4,500 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions w/ claimed_amount | n30_amtcur | 4,500 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions w/ claimed_amount | n30_amt1pct | 4,500 | 100.00% | 0.00% | 0.00% | 0.00% |
| Transactions | n30 customer-any-product | 13,580 | 50.19% | 28.73% | 20.82% | 0.27% |
| Fees | n1 | 13,553 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees | n7 | 13,553 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees | n30 | 13,553 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees | n30_pendrev | 13,553 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees | n30_fraud | 13,553 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees w/ claimed_amount | n30 | 4,457 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees w/ claimed_amount | n30_amt | 4,457 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees w/ claimed_amount | n30_amtcur | 4,457 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees w/ claimed_amount | n30_amt1pct | 4,457 | 100.00% | 0.00% | 0.00% | 0.00% |
| Fees | n30 customer-any-product | 13,553 | 50.81% | 28.94% | 20.05% | 0.20% |

(n1/n7/n30 = same customer+product, 1/7/30 days before creation_date; n30_pendrev / n30_fraud = only Pending/Reversed or is_fraud tx; rows 'w/ claimed_amount' restrict to complaints having claimed_amount: n30_amt = amount == claimed_amount, n30_amtcur = also same currency, n30_amt1pct = within ±1%; 'customer-any-product' = same customer, any product.)

- claimed_amount non-null: 21,751 of all, 4,500 of Transactions complaints.

| category | complaints | claimed_amount non-null | affected_product_id non-null | origin_interaction_id non-null |
|---|---|---|---|---|
| Transactions | 13,580 | 4,500 | 9,001 | 0 |
| Fees | 13,553 | 4,457 | 9,019 | 0 |
| Technical | 13,407 | 4,352 | 8,905 | 0 |
| Branch | 13,361 | 4,223 | 8,808 | 0 |
| Service | 13,194 | 4,219 | 8,837 | 0 |

- Transactions+Fees complaints with claimed_amount (8,957): same customer, ANY product, exact amount, 30d before → 0 tx 100.00%, exactly 1 0.00%, >1 0.00%.
- Same, but ANY time (no window) → 0 tx 100.00%, exactly 1 0.00%, >1 0.00%.
- Transactions complaints with a product: mean 0 / median 0 candidate tx (same customer+product, 30d).
- description mentions a currency amount: 0; any 3+ digit number: 0; a date: 0; contains a merchant_name from that customer's last-30-day transactions: 0. Distinct descriptions: 5 of 67,095.
- origin_interaction_id non-null 0, resolvable to call_center_interactions 0.
- Of 0 complaints joined to their origin interaction: mentioned_products non-null 0; mentioned_products contains affected_product_id 0; same customer 0; interaction before/at complaint 0.
- complaints whose origin interaction has a call transcript: 0.

Sample dispute descriptions (truncated):

- [Transactions / Cargo no reconocido] Queja relacionada con transactions
- [Transactions / Cargo no reconocido] Queja relacionada con transactions

### d. Labels

- **status**: In Process=26,823; Open=20,125; Resolved=13,512; Escalated=3,321; Closed=2,609; Rejected=705
- **case_type**: Complaint=40,452; Claim=16,598; Request=6,761; Suggestion=3,284
- **priority**: Medium=33,439; Low=20,411; High=9,890; Critical=3,355
- **reception_channel**: Call Center=33,761; Email=13,323; Web=9,884; App=6,727; Branch=2,683; Regulator=717
- **sla_breached**: 0=53,600; 1=13,495
- **is_repeat_complainer**: 0=57,009; 1=10,086
- **compensation_granted**: non-null 4,641, >0 4,641, min 10.15, max 500, mean(>0) 253.1
- **resolution** text: non-null 15,310, distinct 5

| status | rows | compensation non-null | compensation>0 | resolution non-null | resolution_date non-null |
|---|---|---|---|---|---|
| In Process | 26,823 | 0 | 0 | 0 | 0 |
| Open | 20,125 | 0 | 0 | 0 | 0 |
| Resolved | 13,512 | 3,874 | 3,874 | 12,833 | 12,880 |
| Escalated | 3,321 | 0 | 0 | 0 | 0 |
| Closed | 2,609 | 767 | 767 | 2,477 | 2,469 |
| Rejected | 705 | 0 | 0 | 0 | 0 |

| category | rows | Resolved | Rejected | compensation>0 |
|---|---|---|---|---|
| Transactions | 13,580 | 2,780 | 125 | 995 |
| Fees | 13,553 | 2,738 | 133 | 945 |
| Technical | 13,407 | 2,670 | 140 | 894 |
| Branch | 13,361 | 2,675 | 155 | 935 |
| Service | 13,194 | 2,649 | 152 | 872 |

Dispute complaints by status: In Process=5,407 (comp>0 0); Open=4,040 (comp>0 0); Resolved=2,780 (comp>0 822); Escalated=677 (comp>0 0); Closed=551 (comp>0 173); Rejected=125 (comp>0 0)

Top category/subcategory:

| category | subcategory | rows |
|---|---|---|
| Transactions | Cargo no reconocido | 12,297 |
| Fees | Cobro indebido | 12,194 |
| Technical | Problema con app | 12,128 |
| Branch | Atención en sucursal | 11,892 |
| Service | Calidad de servicio | 11,886 |
| Branch | None | 1,469 |
| Fees | None | 1,359 |
| Service | None | 1,308 |
| Transactions | None | 1,283 |
| Technical | None | 1,279 |

Top resolution texts:

| resolution (100 chars) | rows |
|---|---|
| Se revisó el caso y se realizó el ajuste correspondiente ... | 3,132 |
| Se escaló a área correspondiente y se aplicó la solución ... | 3,098 |
| Se brindó explicación detallada al cliente y se resolvió ... | 3,078 |
| Se otorgó compensación al cliente por las molestias ocasi... | 3,034 |
| Se verificó la información y se procedió con la correcció... | 2,968 |

### e. Channel, timing, escalation, fairness splits

- resolution_days: non-null 15,363, min 1.0, max 30.0, mean 15.6. Timestamps available: creation, assignment, first_response, resolution, closing; sla_breached flag; status 'Escalated'; call_center_interactions.was_escalated.

| country | segment | complaints | Resolved | comp>0 | avg resolution_days |
|---|---|---|---|---|---|
| Argentina | Basic | 7,998 | 1,633 | 520 | 15.34 |
| Argentina | Plus | 3,320 | 649 | 244 | 15.77 |
| Argentina | Premium | 1,341 | 261 | 93 | 15.47 |
| Argentina | Student | 677 | 130 | 44 | 16.02 |
| Colombia | Basic | 12,151 | 2,413 | 880 | 15.49 |
| Colombia | Plus | 5,129 | 1,068 | 370 | 15.9 |
| Colombia | Premium | 2,090 | 438 | 139 | 15.37 |
| Colombia | Student | 1,014 | 199 | 64 | 15.87 |
| México | Basic | 19,986 | 4,038 | 1,373 | 15.61 |
| México | Plus | 8,386 | 1,699 | 591 | 15.62 |
| México | Premium | 3,333 | 659 | 204 | 16 |
| México | Student | 1,670 | 325 | 119 | 15.45 |

### f. Follow-up diagnostics (why the customer+product join fails, and alternatives)

- complaints with affected_product_id: 44,570; of those, the product is owned by the complaining customer: **0** (0.00%). So `affected_product_id` points to another customer's product, and customer+product joins can't match.
- Transactions complaints, **product only** (ignoring customer), 1d window: n=9,001: 0 → 98.99%, 1 → 1.01%, 2–5 → 0.00%, >5 → 0.00%
- Transactions complaints, **product only** (ignoring customer), 7d window: n=9,001: 0 → 93.05%, 1 → 6.77%, 2–5 → 0.19%, >5 → 0.00%
- Transactions complaints, **product only** (ignoring customer), 30d window: n=9,001: 0 → 74.39%, 1 → 21.12%, 2–5 → 4.49%, >5 → 0.00%
- Transactions complaints, **customer only** (any product), 1d window: n=13,580: 0 → 97.13%, 1 → 2.82%, 2–5 → 0.05%, >5 → 0.00%
- Transactions complaints, **customer only** (any product), 7d window: n=13,580: 0 → 83.28%, 1 → 14.84%, 2–5 → 1.88%, >5 → 0.00%
- Transactions complaints, **customer only** (any product), 30d window: n=13,580: 0 → 50.19%, 1 → 28.73%, 2–5 → 20.82%, >5 → 0.27%
- Transactions complaints, customer only, only Pending/Reversed tx, 30d: n=13,580: 0 → 97.36%, 1 → 2.58%, >1 → 0.07%
- Transactions complaints with claimed_amount: 4,500; ≥1 tx for the same customer within ±1% of claimed_amount at ANY time/product: 251 (5.58%).
- claimed_amount by currency (Transactions complaints): ARS: n=1,061, min 62.53, median 2,502, max 4,986; COP: n=1,080, min 55.8, median 2,409, max 4,998; MXN: n=1,081, min 55.06, median 2,669, max 5,000; USD: n=1,080, min 76.19, median 2,537, max 4,991; None: n=198, min 82.7, median 2,755, max 4,962
- transaction amount by currency: ARS: n=792,585, median 1.633e+05; COP: n=1,194,444, median 1,867,136; USD: n=2,437,979, median 467.1
- complaint currency × customer country: Argentina/ARS=1,082; Argentina/COP=1,070; Argentina/MXN=1,124; Argentina/USD=1,051; Colombia/ARS=1,711; Colombia/COP=1,634; Colombia/MXN=1,650; Colombia/USD=1,682; México/ARS=2,609; México/COP=2,752; México/MXN=2,713; México/USD=2,698
- transaction_country × currency: Argentina/ARS=752,794; Argentina/COP=12,059; Argentina/USD=102,708; Brazil/ARS=7,859; Brazil/COP=11,887; Brazil/USD=20,726; Colombia/ARS=7,983; Colombia/COP=1,134,801; Colombia/USD=146,719; Mexico/ARS=7,995; Mexico/COP=11,905; Mexico/USD=20,615; México/USD=2,105,794; Spain/ARS=7,923; Spain/COP=11,790; Spain/USD=20,829; USA/ARS=8,031; USA/COP=12,002; USA/USD=20,588
- rows that are duplicates if you ignore the PK: transactions=0; complaints=0
- looser duplicate-charge definitions: same customer+merchant ≤10 min (any amount) 3; ≤24 h 671; same customer+product ≤10 min (any amount) 390; same customer+amount ≤24 h (any merchant) 0. merchant_name has only 24 distinct values (generic names).
- transaction_date − process_date ranges from 6:00:00 to 1 day, 6:00:00. Every timestamp is 6–30 h after 00:00 of process_date, which looks like a fixed +6 h (UTC vs UTC-6) shift, not late arrival.
- fraud_score ≥ 30 by is_fraud: is_fraud=False: rows 4,420,692, score non-null 3,536,426, ≥30 609 (0.02% of non-null), score null 884,266; is_fraud=True: rows 4,316, score non-null 3,425, ≥30 2,373 (69.28% of non-null), score null 891
- Transactions complaints with a call-center interaction by the same customer in the 7 d before: 389. interactions.mentioned_products non-null: 274,341. reason_category: Transaccional=240,056; Producto=150,863; Queja=117,021; Técnico=102,899; Comercial=54,879; Retención=20,578
- Transactions complaints with a final outcome (Resolved/Closed/Rejected): 3,456; Rejected 125; compensation>0 995; Resolved/Closed without compensation 2,336.

| status | rows | closing_date | resolution_date | first_response_date | resolution_satisfaction |
|---|---|---|---|---|---|
| In Process | 26,823 | 0 | 0 | 25,492 | 0 |
| Open | 20,125 | 0 | 0 | 0 | 0 |
| Resolved | 13,512 | 0 | 12,880 | 12,861 | 0 |
| Escalated | 3,321 | 0 | 0 | 0 | 0 |
| Closed | 2,609 | 2,481 | 2,469 | 2,500 | 2,484 |
| Rejected | 705 | 0 | 0 | 0 | 0 |

## 6. Blockers / risks

1. **No reliable complaint → transaction link (blocker for supervised dispute matching).** There is no transaction_id. affected_product_id belongs to the complaining customer in 0 of 44,570 cases, and customer+product+window matches 0% of complaints. The only workable key is customer + time window: for Transactions complaints over 30 d, 28.73% have exactly 1 candidate, 21.08% have 2+, and 50.19% have none. claimed_amount doesn't help: it's non-null for only 4,500 of 13,580 Transactions complaints, falls in a narrow range whatever the currency, and matches a customer's transaction (±1%) in only 5.58%, which looks like chance. origin_interaction_id is 100.0% null, and descriptions/resolutions are templated (5 / 5 distinct texts). Treat any complaint↔transaction pairing as synthetic/heuristic.
2. **Few, weak outcome labels.** Of 13,580 Transactions complaints, 3,456 have a final status, only 125 are Rejected and 995 got compensation. compensation_granted is 93.1% null overall and resolution_satisfaction 96.3% null. Resolved/Rejected/compensation rates are nearly identical across categories, countries and segments (see 5d/5e), which suggests they were generated independently of the case, so a model will learn little from them.
3. **The duplicate/quality issues the dictionary describes aren't in the data; the real issues are elsewhere.** Duplicate-PK rows across all tables: 0; fully duplicated rows: 0; transaction duplicates if you ignore the PK: 0. The dictionary claims ~2%. Strict duplicate-charge candidates (same customer+merchant+amount ≤24 h): 0; the looser same customer+merchant ≤10 min gives 3. A duplicate-charge feature would have to be injected/simulated. Row counts differ from the dictionary (see 2b), transaction timestamps carry a fixed +6 h shift vs process_date, and complaint currencies are independent of customer country. transactions have no MXN currency rows (currencies: ARS, COP, USD), and transaction_country uses inconsistent labels (Argentina, Brazil, Colombia, Mexico, México, Spain, USA).
4. **What is usable:** fraud_score is present (20.0% null) and separates is_fraud well (≥30 on 69.28% of scored fraud vs 0.02% of scored non-fraud). But is_fraud is rare (4316 of 4,425,008 tx). Pending and Reversed statuses are present and clean. Fairness splits exist: customers.country/segment/detected_accent, complaints.reception_channel/priority/sla_breached. Resolution timing exists (resolution_days, first_response/resolution/closing dates, with no ordering violations).
5. **PII:** customers (document_number, names, date_of_birth, email, phones, address, postal_code), products.product_number, agent/branch contact details, digital_events.ip_address, transaction lat/long, and free text (transcripts, survey comments). Mask these before sending anything to an LLM.

## 7. Dispute-intake pipeline outputs (added 2026-09-29)

Full details are in `pipeline/README.md`. All numbers below are computed by the pipeline run.
- Silver contract: 0 contract violations. Dedupe: 0 exact duplicates and 0 PK conflicts in transactions (4,425,008), customers (150,000) and products (400,000).
- Country normalization: `México` → `Mexico`. Transactions by country after normalization: Mexico 2,146,309; Colombia 1,289,503; Argentina 867,561; USA 40,621; Spain 40,542; Brazil 40,472. Customers: Mexico 74,907; Colombia 45,251; Argentina 29,842.
- Timestamp offset: fixed +6 h (`transaction_ts_local = transaction_date − 6h`), which keeps every row inside its process_date. 51 rows fall exactly on the closing midnight.
- Fraud-triage table (Approved + Declined only): 4,291,915 rows. Split by UTC time: train 3,004,340 (3,028 positives), val 643,787 (599), test 643,788 (574). Cutoffs 2025-07-26 00:30:11 and 2026-01-07 00:26:41 UTC.
- Baseline `fraud_score >= 30` on test: 422 flagged, 334 true positives, so precision 0.7915 and recall 0.5819 over 574 positives.
- Synthetic duplicate fixture: 300 cases (181 true_duplicate, 119 legitimate_repeat), all `is_synthetic`. It exists because the real data has 0 duplicate charges.

## 8. Masked copies in Databricks (added 2026-10-03)

Every layer that goes to Jaime's Databricks workspace is masked on our computer first, so no unmasked data leaves it. Each table is built from a list of allowed columns, so any column not on the list is dropped by default. Raw IDs are replaced with the same salted pseudonymous keys gold uses, so the layers still join. Before upload, every Parquet file is scanned in full, and the upload stops if it finds a PII column name, a raw ID (`CLI-`, `PRD-`, `TRX-`), an email, a phone number, a document number, a name or a local path.

| Table (bronze and silver) | Rows | Dropped | Replaced with salted keys | Kept |
|---|---|---|---|---|
| `transactions_masked` | 4,425,008 | `latitude`, `longitude` | `transaction_id`, `product_id`, `customer_id` | all other columns, including `merchant_name` and `transaction_city` (same as gold) |
| `customers_masked` | 150,000 | `document_number`, `document_type`, `first_name`, `last_name`, `date_of_birth`, `gender`, `email`, `mobile_phone`, `landline_phone`, `address`, `city`, `state`, `postal_code` | `customer_id` | `country`, `detected_accent`, `segment`, `credit_score`, `estimated_monthly_income`, `occupation`, `marital_status`, `education_level`, `registration_date`, `registration_branch_id`, `customer_status`, `last_updated`, `accepts_marketing` |
| `products_masked` | 400,000 | `product_number` | `product_id`, `customer_id` | all other columns |

In bronze, the `_source_file` lineage column is cut down to its relative path inside `raw/`. The kept customer attributes don't identify a person on their own. They stay in so fairness can be checked across income, occupation and other groups. Row counts in Databricks were verified with `count(*)` against the local DuckDB run.
