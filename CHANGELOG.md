# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-26

### Added

#### Business Registry & Authentication
- Gestione completa Business Registry ACube
- Generazione e rinnovo automatico token JWT (validità 24 ore)
- Decodifica token per debugging
- Credenziali sicure con password crittografate

#### Connessioni Bancarie
- Flusso OAuth per connessione sicura con banche
- Supporto multi-account bancari per azienda
- Gestione account: abilitazione/disabilitazione
- Eliminazione completa connessioni bancarie
- Test mode con banche fake per sandbox

#### Transazioni Bancarie
- Import automatico transazioni in Bank Transaction
- Filtri avanzati per data, account, importo
- Transaction Log completo per audit
- Integrazione nativa con Bank Reconciliation Tool
- Salvataggio raw data JSON per debugging

#### Pagamenti SEPA
- Bonifici SEPA da Purchase Invoice
- SEPA Instant con completamento in pochi secondi
- Validazione automatica paese IBAN per SEPA
- IBAN Enrichment: creazione automatica Bank/Bank Account
- Payment Entry automatico da webhook
- Callback page dopo autorizzazione pagamento
- Mode of Payment configurabile per company
- Tracking completo UUID e End-to-End ID

#### Reporting & UI
- Report Authorized Bank Accounts con ordinamento per saldo
- Workspace dedicato OpenBanking
- Interfaccia intuitiva con pulsanti contestuali
- Modal con dettagli completi API
- Auto-return URL dopo autorizzazione
- Permessi granulari per utenti non amministratori

#### API & Integrations
- Client API centralizzato (principio DRY)
- Gestione webhook ACube (connect, reconnect, payment)
- Scheduled task per sync automatico dati
- IBAN validation API con provider multipli
- Custom fields su Bank Transaction per dati ACube

### Security
- Password crittografate con sistema Frappe
- Token JWT con refresh automatico
- Validazione pattern per email e password
- Raw data storage per audit trail completo

### Documentation
- README completo con guida installazione
- Documentazione API endpoints
- Troubleshooting guide
- Esempi d'uso per ogni feature
- Diagrammi struttura applicazione

### Developer Experience
- Pre-commit hooks configurati (ruff, eslint, prettier)
- Pyproject.toml con linting rules
- Codice seguente principi DRY e KISS
- No fallback: errori sempre espliciti
- Type annotations Python

[1.0.0]: https://github.com/Solede-SA/solede_openbanking/releases/tag/v1.0.0
