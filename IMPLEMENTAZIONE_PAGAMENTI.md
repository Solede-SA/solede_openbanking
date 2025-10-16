# Implementazione Sistema Pagamenti Open Banking

## Panoramica

Sistema completo per eseguire bonifici SEPA tramite Open Banking API direttamente da Purchase Invoice.

## Principi Implementativi

- **DRY**: Massimo riutilizzo del codice esistente (ACubeAPIClient, iban_enrichment, webhooks)
- **KISS**: Flusso lineare e chiaro senza complessità inutili
- **NO FALLBACK**: Ogni errore viene mostrato all'utente, nessuna gestione silente

## Componenti Implementati

### 1. DocType: OpenBanking Payment
**File**: `solede_openbanking/doctype/openbanking_payment/`

**Campi principali**:
- `uuid`: UUID del pagamento da ACube API
- `payment_direction`: outbound/inbound
- `status`: pending, processing, completed, failed, cancelled
- `system`: sepa, sepa-instant
- `amount`, `currency_code`, `description`
- `reference_doctype`, `reference_name`: Collegamento a Purchase Invoice
- `supplier`, `creditor_name`, `creditor_iban`
- `account_uuid`: Account OpenBanking da cui pagare
- `connect_url`: URL per autorizzazione
- `error_message`, `raw_response`

**Validazioni**:
- Amount > 0
- SEPA Instant max 100.000 EUR
- Aggiornamento automatico documento di riferimento

### 2. API Module: payments.py
**File**: `solede_openbanking/api/payments.py`

**Funzioni**:

#### `get_supplier_bank_accounts(supplier_name)`
Recupera tutti i Bank Account del fornitore.

#### `get_company_openbanking_accounts(company)`
Recupera gli account OpenBanking abilitati della company.

#### `initiate_sepa_payment(reference_doctype, reference_name, account_uuid, creditor_iban, creditor_name, use_instant)`
Avvia un pagamento SEPA:
1. Valida documento di riferimento
2. Crea client API con ACubeAPIClient (DRY)
3. Chiama `/payments/send/sepa` o `/payments/send/sepa-instant`
4. Crea record OpenBanking Payment
5. Ritorna connect_url per autorizzazione

#### `get_payment_status(payment_uuid)`
Aggiorna status pagamento da API.

#### `create_or_get_supplier_bank_account(supplier_name, iban, account_name)`
Riutilizza completamente `create_bank_and_account_from_iban` (DRY).

### 3. Client-side: purchase_invoice.js
**File**: `solede_openbanking/public/js/purchase_invoice.js`

**Funzionalità**:

#### Bottone "Esegui Bonifico"
Visibile solo se:
- Purchase Invoice è submitted (docstatus === 1)
- Outstanding amount > 0

#### Flusso Utente:
1. Click bottone → Recupera Bank Account fornitore
2. Se esiste: Mostra dialog selezione IBAN + opzione "Nuovo IBAN"
3. Se non esiste: Mostra dialog inserimento IBAN
4. Validazione real-time IBAN (riutilizza logica da supplier.js - DRY)
5. Selezione account OpenBanking company
6. Checkbox "Bonifico Istantaneo"
7. Avvio pagamento → Apertura connect_url in popup
8. Refresh automatico per mostrare status

#### Dialog IBAN
Riutilizza completamente la logica da `supplier.js`:
- Validazione real-time
- Creazione automatica Bank Account
- Alert per IBAN già esistente

### 4. Webhook Handler Aggiornato
**File**: `solede_openbanking/api/webhooks.py`

#### `handle_payment_webhook(payload, company, log_name)`
Gestisce eventi payment da ACube:
1. Trova OpenBanking Payment per UUID
2. Aggiorna status dal payload
3. Gestisce errori (salva error_message)
4. Se status = "completed" → Crea Payment Entry

#### `create_payment_entry_from_payment(payment_doc)`
Crea automaticamente Payment Entry:
1. Verifica Purchase Invoice esiste
2. Verifica outstanding_amount > 0
3. Usa `get_payment_entry` di ERPNext (DRY)
4. Configura campi (amount, reference_no, remarks)
5. Submit automatico
6. Notifica utente via realtime

### 5. Pagina Callback
**File**: `solede_openbanking/templates/pages/payment_callback.py` e `.html`

**Funzionalità**:
- Riceve payment_uuid da query string
- Recupera OpenBanking Payment
- Mostra status con icona e colore appropriato:
  - ✅ completed: verde
  - ❌ failed: rosso + dettagli errore
  - ⏳ pending: arancione
  - 🔄 processing: blu + auto-refresh ogni 5 secondi
- Link per tornare al documento di riferimento

### 6. Custom Fields Purchase Invoice
**File**: `solede_openbanking/fixtures/custom_field.json`

**Campi aggiunti**:
- `openbanking_payment` (Link): Collegamento a OpenBanking Payment
- `openbanking_status` (Data): Status pagamento (fetch da openbanking_payment.status)
  - In list view e standard filter
  - Aggiornato automaticamente via webhook

### 7. Hooks Aggiornati
**File**: `solede_openbanking/hooks.py`

Aggiunto:
```python
doctype_js = {
    "Bank Transaction": "public/js/bank_transaction.js",
    "Supplier": "public/js/supplier.js",
    "Purchase Invoice": "public/js/purchase_invoice.js"  # NUOVO
}
```

## Flusso Completo

### 1. Avvio Pagamento
```
User → Click "Esegui Bonifico"
  ↓
Sistema → Recupera/Crea Bank Account fornitore (IBAN)
  ↓
User → Seleziona Account OpenBanking company
  ↓
User → Conferma importo e tipo (SEPA/SEPA Instant)
  ↓
Sistema → Chiama API ACube POST /payments/send/sepa
  ↓
ACube → Ritorna {uuid, connectUrl}
  ↓
Sistema → Crea OpenBanking Payment (status: pending)
  ↓
User → Redirect a connectUrl (banca)
```

### 2. Autorizzazione Banca
```
User → Accede a sito banca
  ↓
User → Autorizza pagamento
  ↓
Banca → Esegue bonifico
  ↓
Banca → Notifica ACube
```

### 3. Callback e Finalizzazione
```
ACube → Invia webhook al nostro endpoint
  ↓
Sistema → handle_payment_webhook()
  ↓
Sistema → Trova OpenBanking Payment per UUID
  ↓
Sistema → Aggiorna status a "completed"
  ↓
Sistema → create_payment_entry_from_payment()
  ↓
Sistema → Crea Payment Entry automatico
  ↓
Sistema → Purchase Invoice.outstanding_amount = 0
  ↓
User → Notifica realtime "Payment Entry creato"
```

### 4. Monitoraggio
```
User → Apre Purchase Invoice
  ↓
Sistema → Mostra badge status pagamento
  ↓
User → Click "Aggiorna Status Pagamento"
  ↓
Sistema → Chiama API GET /payments/{uuid}
  ↓
Sistema → Aggiorna OpenBanking Payment
  ↓
Sistema → Refresh Purchase Invoice
```

## Installazione

### 1. Migrare DocType
```bash
bench --site [site-name] migrate
```

### 2. Importare Fixtures
```bash
bench --site [site-name] import-doc fixtures/custom_field.json
```

### 3. Build Assets
```bash
bench build --app solede_openbanking
```

### 4. Riavviare
```bash
bench restart
```

## Configurazione

### 1. OpenBanking Settings
Assicurati di avere configurato:
- API URL
- Credentials
- Account OpenBanking abilitati

### 2. Webhook ACube
Configura webhook URL in ACube dashboard:
```
https://[your-domain]/api/method/solede_openbanking.api.webhooks.acube_webhook
```

### 3. Return URL
Il sistema usa automaticamente:
```
https://[your-domain]/payment-callback?payment_uuid={uuid}
```

## Testing

### Test Flow Completo
1. Crea Purchase Invoice per fornitore
2. Submit Purchase Invoice
3. Click "Esegui Bonifico"
4. Seleziona/Inserisci IBAN fornitore
5. Seleziona Account OpenBanking
6. Conferma avvio bonifico
7. Autorizza su sito banca (sandbox)
8. Verifica webhook ricevuto
9. Verifica Payment Entry creato
10. Verifica Purchase Invoice pagata

### Simulare Webhook (Development)
```python
import frappe
import json

payload = {
    "fiscalId": "12345678901",
    "paymentUuid": "uuid-del-pagamento",
    "paymentDirection": "outbound",
    "paymentStatus": "completed",
    "amount": "100.00",
    "currencyCode": "EUR",
    "endToEndId": "E2E123456"
}

frappe.set_user("Administrator")
from solede_openbanking.api.webhooks import handle_payment_webhook
result = handle_payment_webhook(payload, "Your Company", "test-log")
print(result)
```

## Estensioni Future

### 1. Pagamenti Multipli
Supportare pagamento multiplo di più Purchase Invoice contemporaneamente.

### 2. Scheduling
Schedulare pagamenti per data futura.

### 3. Approvazione
Workflow di approvazione multi-livello per pagamenti sopra soglia.

### 4. Notifiche
Email automatica a fornitore quando pagamento completato.

### 5. Riconciliazione Automatica
Collegare automaticamente Bank Transaction creata dal pagamento.

## Troubleshooting

### Errore: "OpenBanking Settings not found"
Assicurati di aver configurato OpenBanking Settings per la company.

### Errore: "No account OpenBanking configurato"
Abilita almeno un account in OpenBanking Settings → Accounts.

### Webhook non ricevuto
1. Verifica URL webhook in ACube dashboard
2. Verifica firma HTTP valida
3. Controlla ACube Webhook Log per errori

### Payment Entry non creato automaticamente
1. Verifica webhook ricevuto (ACube Webhook Log)
2. Verifica status OpenBanking Payment = "completed"
3. Controlla Error Log per eccezioni

### Status "processing" bloccato
1. Click "Aggiorna Status Pagamento" in Purchase Invoice
2. Controlla status su ACube dashboard
3. Verifica transazione su estratto conto banca

## File Modificati/Creati

### Nuovi File
- `solede_openbanking/doctype/openbanking_payment/*`
- `solede_openbanking/api/payments.py`
- `solede_openbanking/public/js/purchase_invoice.js`
- `solede_openbanking/templates/pages/payment_callback.py`
- `solede_openbanking/templates/pages/payment_callback.html`

### File Modificati
- `solede_openbanking/api/webhooks.py` (handle_payment_webhook + create_payment_entry_from_payment)
- `solede_openbanking/hooks.py` (aggiunto doctype_js per Purchase Invoice)
- `solede_openbanking/fixtures/custom_field.json` (aggiunti campi Purchase Invoice)

## Supporto

Per problemi o domande:
1. Controlla Error Log in ERPNext
2. Verifica ACube Webhook Log
3. Controlla ACube Transaction Log
4. Consulta documentazione ACube API: https://docs.acubeapi.com
