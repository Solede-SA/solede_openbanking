# Solede OpenBanking

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Frappe](https://img.shields.io/badge/Frappe-v15+-orange.svg)](https://github.com/frappe/frappe)
[![ERPNext](https://img.shields.io/badge/ERPNext-v15+-blue.svg)](https://github.com/frappe/erpnext)

Frappe app per l'integrazione con ACube Open Banking API. Questa app permette di integrare le tue aziende ERPNext con le banche europee attraverso gli standard PSD2 Open Banking.

## ✨ Funzionalità

### Gestione Autenticazione
- **Token JWT Automatico** - Generazione e rinnovo automatico dei token (validità 24 ore)
- **Decodifica Token** - Visualizzazione dettagli token per debugging
- **Credenziali Sicure** - Password crittografate usando i meccanismi di sicurezza di Frappe

### Business Registry
- **Creazione Business Registry** - Registrazione azienda presso ACube Open Banking
- **Gestione per Company** - Configurazione separata per ogni azienda ERPNext
- **Info Registry** - Visualizzazione dettagli completi del Business Registry

### Connessioni Bancarie
- **Flusso OAuth** - Connessione sicura con autorizzazione bancaria
- **Multi-Account** - Supporto per più account bancari per azienda
- **Gestione Account** - Abilitazione/disabilitazione account autorizzati
- **Eliminazione Account** - Rimozione completa delle connessioni bancarie
- **Test Mode** - Ambiente sandbox con banche fake per test

### Transazioni Bancarie
- **Import Transazioni** - Importazione automatica movimenti bancari in Bank Transaction
- **Filtri Avanzati** - Ricerca per data, account, importo
- **Transaction Log** - Tracciamento completo di tutte le operazioni
- **Riconciliazione** - Integrazione nativa con Bank Reconciliation Tool di ERPNext
- **Dati Completi** - Salvataggio raw data JSON per audit e debugging

### Reporting
- **Authorized Bank Accounts Report** - Visualizzazione conti autorizzati in sola lettura
- **Ordinamento per Balance** - Conti ordinati per saldo decrescente
- **Permessi Granulari** - Accesso report anche per utenti non amministratori
- **Workspace Dedicato** - Interfaccia centralizzata per tutte le operazioni

### UI/UX
- **Interfaccia Intuitiva** - Pulsanti contestuali e dropdown organizzati
- **Modal con Dettagli** - Visualizzazione completa dati API per ogni account
- **Auto-Return URL** - Redirect automatico dopo autorizzazione bancaria
- **Validazione Password** - Controlli pattern per password Business Registry

## 📋 Requisiti

- Frappe Framework v15+
- ERPNext v15+
- Python 3.10+
- Account ACube Open Banking valido
- Company con Partita IVA (Tax ID) configurata

## 🚀 Installazione

### 1. Scarica l'app

```bash
cd frappe-bench
bench get-app https://github.com/Solede-SA/solede_openbanking.git
```

### 2. Installa sul sito

```bash
bench --site your-site.local install-app solede_openbanking
```

### 3. Migra il database

```bash
bench --site your-site.local migrate
```

### 4. Riavvia il bench

```bash
bench restart
```

## ⚙️ Configurazione

### 1. Configurazione Company

Prima di tutto, assicurati che il documento **Company** abbia:
- **Tax ID** (Partita IVA) configurato correttamente
- **Company Name** compilato

Questi dati verranno usati per creare il Business Registry.

### 2. OpenBanking Settings

Naviga in **OpenBanking > OpenBanking Settings** e crea un nuovo documento:

#### Configurazione API
- **Company**: Seleziona la tua azienda
- **Common API URL**: Endpoint autenticazione
  - Sandbox: `https://common-sandbox.api.acubeapi.com`
  - Production: `https://common.api.acubeapi.com`
- **Open Banking API URL**: Endpoint operazioni
  - Sandbox: `https://ob-sandbox.api.acubeapi.com`
  - Production: `https://ob.api.acubeapi.com`

#### Credenziali
- **Email**: Email del tuo account ACube
- **Password**: Password del tuo account ACube

## 📖 Guida all'Uso

### Step 1: Genera Token

1. Apri il documento **OpenBanking Settings** della tua Company
2. Clicca **Generate Token**
3. Il token verrà generato e salvato automaticamente
4. Puoi visualizzare i dettagli del token nella sezione "Token Information"

Il token ha validità di 24 ore e viene rinnovato automaticamente quando necessario.

### Step 2: Crea Business Registry

1. Clicca **Actions > Create Business Registry**
2. Inserisci una password per il Business Registry (requisiti: maiuscola, minuscola, numero, carattere speciale)
3. Conferma la creazione

⚠️ **Attenzione**: Questa operazione comporta un addebito da parte di ACube.

Il sistema userà:
- **Fiscal ID**: dalla Partita IVA della Company
- **Business Name**: dal nome della Company
- **Email**: dalle OpenBanking Settings

### Step 3: Connetti Banca

1. Clicca **Actions > Connect Bank Account**
2. Configura i parametri (opzionali):
   - **Bank Manager Email**: Email del responsabile
   - **Consent Days**: Durata consenso (1-180 giorni, default: 180)
   - **Test Mode**: Attiva per usare banca fake in sandbox
3. Clicca **Connect**

Si aprirà una nuova finestra dove potrai:
1. Selezionare la banca
2. Autenticarti con le credenziali bancarie
3. Autorizzare l'accesso agli account

Il sistema usa automaticamente l'URL corrente come return URL.

### Step 4: Aggiorna Lista Account

Dopo aver completato l'autorizzazione:
1. Clicca **Refresh Accounts**
2. Gli account autorizzati verranno mostrati nella tab "Authorized Bank Accounts"

Per ogni account puoi:
- **View Details**: Visualizzare tutti i dati dell'account
- **Enable/Disable**: Abilitare o disabilitare l'account
- **Delete**: Eliminare la connessione (solo se disabilitato)

### Step 5: Importa Transazioni

1. Naviga in **OpenBanking > OpenBanking Settings**
2. Clicca **Actions > Import Transactions**
3. Configura i filtri:
   - **Account**: Seleziona un account specifico o lascia vuoto per tutti
   - **From Date**: Data inizio
   - **To Date**: Data fine
4. Clicca **Import**

Le transazioni verranno importate in:
- **Bank Transaction**: Per la riconciliazione
- **ACube Transaction Log**: Per il tracciamento

### Visualizza Report

Naviga in **OpenBanking Workspace** e clicca su **Authorized Bank Accounts** per visualizzare tutti gli account autorizzati ordinati per saldo decrescente.

Il report è accessibile anche a utenti con ruolo "Accounts User" o "Accounts Manager".

## 📁 Struttura

```
solede_openbanking/
├── api/
│   ├── authentication.py        # Gestione JWT token
│   ├── business_registry.py     # Business Registry e operazioni
│   ├── client.py                # Client API centralizzato
│   └── utils.py                 # Utility functions
├── solede_openbanking/
│   ├── doctype/
│   │   ├── openbanking_settings/
│   │   │   ├── openbanking_settings.json
│   │   │   ├── openbanking_settings.py
│   │   │   └── openbanking_settings.js
│   │   ├── openbanking_account/
│   │   │   ├── openbanking_account.json
│   │   │   └── openbanking_account.py
│   │   └── acube_transaction_log/
│   │       ├── acube_transaction_log.json
│   │       └── acube_transaction_log.py
│   ├── report/
│   │   └── authorized_bank_accounts/
│   │       ├── authorized_bank_accounts.json
│   │       └── authorized_bank_accounts.py
│   └── workspace/
│       └── openbanking/
│           └── openbanking.json
├── public/
│   └── js/
│       └── openbanking_helpers.js  # Helper JavaScript
├── fixtures/                       # Custom fields e configurazioni
├── hooks.py
└── README.md
```

## 🔌 API Endpoints

### Autenticazione
| Endpoint | Method | Descrizione |
|----------|--------|-------------|
| `/login` | POST | Genera token JWT |

### Business Registry
| Endpoint | Method | Descrizione |
|----------|--------|-------------|
| `/business-registry` | POST | Crea Business Registry |
| `/business-registry/{fiscalId}` | GET | Info Business Registry |
| `/business-registry/{fiscalId}/connect` | POST | Avvia connessione banca |

### Account
| Endpoint | Method | Descrizione |
|----------|--------|-------------|
| `/business-registry/{fiscalId}/accounts` | GET | Lista account autorizzati |
| `/accounts/{uuid}` | PUT | Abilita/disabilita account |
| `/accounts/{uuid}` | DELETE | Elimina account |

### Transazioni
| Endpoint | Method | Descrizione |
|----------|--------|-------------|
| `/business-registry/{fiscalId}/transactions` | GET | Recupera transazioni |

## 🔐 Sicurezza

- **Password Crittografate**: Uso del campo Password di Frappe per crittografia automatica
- **Token JWT**: Autenticazione Bearer token per tutte le chiamate API
- **Raw Data Storage**: Salvataggio completo JSON per audit trail
- **Validazione Campi**: Controlli pattern per email, password e altri campi critici

## 🎨 Principi di Design

Questa app segue rigorosamente i principi:

- **DRY (Don't Repeat Yourself)**: Codice riutilizzabile e modulare
- **KISS (Keep It Simple, Stupid)**: Soluzioni semplici e dirette
- **No Fallback**: Gli errori vengono sempre mostrati all'utente senza sistemi di fallback
- **Explicit Errors**: Messaggi di errore chiari e dettagliati

## 🗃️ Modello Dati

### OpenBanking Settings (DocType)
Configurazione principale per ogni Company.

**Campi principali:**
- `company` (Link): Company di riferimento
- `api_url` (Data): URL API Common
- `openbanking_api_url` (Data): URL API Open Banking
- `email` (Data): Email account ACube
- `password` (Password): Password crittografata
- `business_registry_created` (Check): Flag creazione registry
- `access_token` (Long Text): Token JWT corrente
- `token_created_at` (Datetime): Data creazione token
- `token_expires_at` (Datetime): Data scadenza token
- `accounts` (Table): Child table con account autorizzati

### OpenBanking Account (Child Table)
Account bancari autorizzati.

**Campi principali:**
- `uuid` (Data): Identificativo univoco ACube
- `iban` (Data): IBAN account
- `bank_display` (Data): Nome banca
- `balance_display` (Data): Saldo formattato
- `enabled` (Check): Stato attivo/disattivo
- `raw_data` (Long Text): JSON completo da API

### ACube Transaction Log (DocType)
Log di tutte le transazioni importate.

**Campi principali:**
- `company` (Link): Company
- `bank_account` (Link): Bank Account ERPNext
- `acube_account_uuid` (Data): UUID account ACube
- `transaction_date` (Date): Data transazione
- `acube_transaction_id` (Data): ID transazione ACube
- `transaction_status` (Data): Stato transazione
- `amount` (Currency): Importo
- `currency` (Link): Valuta
- `import_status` (Select): Pending/Imported/Failed
- `bank_transaction` (Link): Link a Bank Transaction
- `error_message` (Text): Messaggio errore se fallita
- `raw_data` (Long Text): JSON completo

### Custom Fields su Bank Transaction
L'app aggiunge campi custom a Bank Transaction:

- `acube_section` (Section Break): Sezione dati ACube
- `acube_transaction_id` (Data): ID transazione univoco
- `api_source` (Data): Fonte (sempre "ACube")
- `acube_booking_date` (Date): Data registrazione
- `acube_value_date` (Date): Data valuta
- `acube_status` (Data): Stato transazione
- `acube_category` (Data): Categoria
- `acube_raw_data` (Long Text): Dati completi JSON

## 🔧 Funzioni API Principali

### authentication.py

```python
generate_token(company)
# Genera nuovo token JWT

get_valid_token(company)
# Ottiene token valido (rinnova se scaduto)

decode_token_payload(token)
# Decodifica payload JWT per debug
```

### business_registry.py

```python
create_business_registry(company, password)
# Crea Business Registry

get_business_registry_info(company)
# Recupera info Business Registry

start_connect_request(company, return_url, bank_manager_email, days, test_mode)
# Avvia connessione bancaria

get_accounts(company)
# Recupera account autorizzati

toggle_account(company, uuid, enabled)
# Abilita/disabilita account

delete_account(company, uuid)
# Elimina account

import_transactions(company, account_uuid, from_date, to_date)
# Importa transazioni in Bank Transaction
```

### client.py

```python
class ACubeAPIClient:
    # Client centralizzato per chiamate API
    # Gestisce automaticamente:
    # - Autenticazione token
    # - Headers comuni
    # - Error handling
    # - Logging
```

## 🌍 Ambienti

### Sandbox (Testing)
- **Common API**: `https://common-sandbox.api.acubeapi.com`
- **OpenBanking API**: `https://ob-sandbox.api.acubeapi.com`
- Usa **Test Mode** per connetterti a banche fake (country code: XF)

### Production
- **Common API**: `https://common.api.acubeapi.com`
- **OpenBanking API**: `https://ob.api.acubeapi.com`
- Banche reali italiane (country code: IT)

## 🐛 Troubleshooting

### Il token non viene generato
- Verifica che email e password siano corretti
- Controlla che gli URL API siano configurati correttamente
- Verifica i log di sistema per errori dettagliati

### Business Registry fallisce
- Assicurati che la Company abbia Tax ID configurato
- Verifica che il formato Tax ID sia valido (Partita IVA italiana)
- Controlla di avere credito sufficiente su ACube

### Connessione banca non funziona
- Verifica che il Business Registry sia stato creato
- Controlla che la finestra popup non sia bloccata dal browser
- Usa Test Mode in sandbox per fare prove

### Transazioni non vengono importate
- Verifica che l'account sia abilitato
- Controlla che la valuta esista in ERPNext
- Verifica che la valuta della transazione corrisponda a quella del Bank Account
- Controlla ACube Transaction Log per vedere errori specifici

## 🤝 Contributing

I contributi sono benvenuti! Per contribuire:

1. Fai fork del progetto
2. Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. Commit delle modifiche (`git commit -m 'feat: Add some AmazingFeature'`)
4. Push al branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

### Setup Pre-commit

L'app usa `pre-commit` per formattazione e linting:

```bash
cd apps/solede_openbanking
pre-commit install
```

Tool configurati:
- **ruff**: Linting Python
- **eslint**: Linting JavaScript
- **prettier**: Formattazione
- **pyupgrade**: Aggiornamento sintassi Python

### Convenzioni Commit

Usa [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` Nuove funzionalità
- `fix:` Bug fix
- `refactor:` Refactoring codice
- `docs:` Modifiche documentazione
- `test:` Aggiunta/modifica test
- `chore:` Maintenance tasks

## 📝 Changelog

### v1.0.0 (TBD)
- ✨ Gestione completa Business Registry
- ✨ Connessione multi-account bancari
- ✨ Import transazioni con riconciliazione
- ✨ Report conti autorizzati
- ✨ Workspace dedicato OpenBanking
- ✨ Transaction Log completo
- ✨ Client API centralizzato (DRY principle)
- ✨ Test mode con fake banks

## 📄 Licenza

MIT License - vedi il file [LICENSE](LICENSE) per dettagli.

## 👥 Autori

**Solede SA**
- Website: [solede.com](https://solede.com)
- Email: info@solede.com

## 🙏 Credits

- Sviluppato con [Claude Code](https://claude.com/claude-code)
- Basato su [Frappe Framework](https://frappeframework.com/)
- Integrazione [ACube Open Banking API](https://acubeapi.com/)

## 💬 Supporto

Per problemi, domande o richieste di funzionalità:
- Apri una [Issue su GitHub](https://github.com/Solede-SA/solede_openbanking/issues)
- Contatta il team Solede: info@solede.com

## 📚 Risorse Utili

- [Documentazione Frappe](https://frappeframework.com/docs)
- [Documentazione ERPNext](https://docs.erpnext.com/)
- [ACube API Documentation](https://acubeapi.com/docs)
- [PSD2 Open Banking Standard](https://www.europeanpaymentscouncil.eu/what-we-do/psd2)

---

Made with ❤️ by Solede SA
