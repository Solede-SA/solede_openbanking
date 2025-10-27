# Contributing to Solede OpenBanking

Grazie per il tuo interesse nel contribuire a Solede OpenBanking! 🎉

## 📋 Indice

- [Codice di Condotta](#codice-di-condotta)
- [Come Contribuire](#come-contribuire)
- [Setup Ambiente di Sviluppo](#setup-ambiente-di-sviluppo)
- [Convenzioni di Codice](#convenzioni-di-codice)
- [Commit Convention](#commit-convention)
- [Pull Request Process](#pull-request-process)
- [Segnalazione Bug](#segnalazione-bug)
- [Richiesta Feature](#richiesta-feature)

## Codice di Condotta

Questo progetto segue il [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/). Partecipando, ti aspettiamo che tu rispetti questo codice.

## Come Contribuire

Ci sono molti modi per contribuire:

- 🐛 Segnalare bug
- 💡 Proporre nuove funzionalità
- 📝 Migliorare la documentazione
- 🔧 Fixare bug
- ✨ Implementare nuove feature
- 🧪 Scrivere test
- 🌍 Tradurre in altre lingue

## Setup Ambiente di Sviluppo

### Prerequisiti

- Frappe Framework v15+
- ERPNext v15+
- Python 3.10+
- Node.js 18+

### Installazione

1. **Fork del repository**
   ```bash
   # Fai fork su GitHub, poi clona il tuo fork
   cd frappe-bench/apps
   git clone https://github.com/TUO-USERNAME/solede_openbanking.git
   cd solede_openbanking
   ```

2. **Installa l'app**
   ```bash
   bench --site your-site.local install-app solede_openbanking
   ```

3. **Setup pre-commit hooks**
   ```bash
   cd apps/solede_openbanking
   pre-commit install
   ```

4. **Crea branch per la tua feature**
   ```bash
   git checkout -b feature/nome-feature
   ```

### Tool di Sviluppo

L'app usa questi tool (già configurati in `.pre-commit-config.yaml`):

- **ruff**: Linting e formattazione Python
- **eslint**: Linting JavaScript
- **prettier**: Formattazione codice
- **pyupgrade**: Aggiornamento sintassi Python moderna

Per eseguire manualmente:
```bash
# Python linting
ruff check .

# Python formatting
ruff format .

# JavaScript linting
npm run lint

# Tutti i check pre-commit
pre-commit run --all-files
```

## Convenzioni di Codice

### Python

- Seguire **PEP 8** con line length 110 caratteri
- Usare **type hints** quando possibile
- Docstring in formato Google style
- Principio **DRY** (Don't Repeat Yourself)
- Principio **KISS** (Keep It Simple, Stupid)
- **NO fallback**: mostrare sempre errori all'utente

```python
def get_accounts(company: str) -> dict:
    """Recupera account bancari autorizzati.

    Args:
        company: Nome della company ERPNext

    Returns:
        Dict con lista account autorizzati

    Raises:
        frappe.ValidationError: Se company non ha OpenBanking Settings
    """
    settings = frappe.get_doc("OpenBanking Settings", company)
    if not settings.business_registry_created:
        frappe.throw("Business Registry non creato")

    return {"accounts": settings.accounts}
```

### JavaScript

- Usare ES6+ syntax
- Arrow functions quando possibile
- Async/await invece di callbacks
- Nomi variabili descrittivi

```javascript
async function refreshAccounts(frm) {
    const response = await frappe.call({
        method: "solede_openbanking.api.business_registry.get_accounts",
        args: { company: frm.doc.company }
    });

    if (response.message) {
        frm.set_value("accounts", response.message.accounts);
    }
}
```

### Naming Conventions

- **Python files**: `snake_case.py`
- **JavaScript files**: `snake_case.js`
- **DocTypes**: `Title Case`
- **Functions**: `snake_case()`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`

## Commit Convention

Usa [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: Nuova funzionalità
- `fix`: Bug fix
- `docs`: Modifiche documentazione
- `style`: Formattazione (no logic changes)
- `refactor`: Refactoring codice
- `test`: Aggiunta/modifica test
- `chore`: Maintenance tasks
- `perf`: Performance improvements

### Esempi

```bash
feat(payments): add SEPA instant payment support

- Implement instant payment API call
- Add validation for max amount €100,000
- Update UI to show instant option

Closes #42

fix(auth): resolve token refresh race condition

The token refresh was failing when multiple requests
happened simultaneously. Added mutex lock.

Fixes #38

docs(readme): update installation instructions

- Add Python 3.10 requirement
- Clarify ACube account setup steps
```

### Scope Suggeriti

- `auth`: Autenticazione e token
- `registry`: Business Registry
- `accounts`: Account bancari
- `transactions`: Import transazioni
- `payments`: Pagamenti SEPA
- `webhooks`: Gestione webhook
- `api`: API client
- `ui`: Interfaccia utente
- `docs`: Documentazione

## Pull Request Process

1. **Update Documentation**
   - Aggiorna README.md se necessario
   - Aggiungi entry in CHANGELOG.md
   - Commenta il codice complesso

2. **Test Your Changes**
   ```bash
   # Test manuale
   bench --site your-site.local migrate
   bench restart

   # Verifica pre-commit
   pre-commit run --all-files
   ```

3. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

4. **Push to Fork**
   ```bash
   git push origin feature/nome-feature
   ```

5. **Create Pull Request**
   - Vai su GitHub
   - Clicca "New Pull Request"
   - Compila il template:
     - Descrizione chiara delle modifiche
     - Link alle issue correlate
     - Screenshots se UI changes
     - Checklist completata

6. **Code Review**
   - Rispondi ai commenti
   - Fai le modifiche richieste
   - Push aggiornamenti (stesso branch)

7. **Merge**
   - Mantainer farà merge quando approvato
   - La tua feature sarà nella prossima release! 🎉

## Segnalazione Bug

### Prima di Segnalare

- Cerca nelle [Issues esistenti](https://github.com/Solede-SA/solede_openbanking/issues)
- Verifica di usare l'ultima versione
- Testa in ambiente sandbox se possibile

### Template Bug Report

```markdown
**Descrizione Bug**
Descrizione chiara del problema.

**Come Riprodurre**
1. Vai a '...'
2. Clicca su '...'
3. Scroll down to '...'
4. Vedi errore

**Comportamento Atteso**
Cosa ti aspettavi che succedesse.

**Screenshots**
Se applicabile, aggiungi screenshots.

**Ambiente:**
- Frappe Version: [es. v15.10.0]
- ERPNext Version: [es. v15.8.0]
- App Version: [es. v1.0.0]
- Browser: [es. Chrome 120]
- OS: [es. Ubuntu 22.04]

**Log di Errore**
```
Paste error log here
```

**Contesto Aggiuntivo**
Qualsiasi altra informazione utile.
```

## Richiesta Feature

### Template Feature Request

```markdown
**La tua feature risolve un problema?**
Descrizione chiara del problema. Es. "Sono frustrato quando [...]"

**Descrivi la soluzione che vorresti**
Descrizione chiara di cosa vorresti che succedesse.

**Descrivi alternative considerate**
Altre soluzioni o feature che hai considerato.

**Use Case**
Scenario d'uso concreto per la feature.

**Contesto Aggiuntivo**
Screenshots, mockup, o altri riferimenti.
```

## Licenza

Contribuendo a questo progetto, accetti che i tuoi contributi saranno rilasciati sotto la licenza **GNU Affero General Public License v3.0**.

Tutti i file devono includere l'header copyright:

```python
# Copyright (c) 2024-2025, Solede SA and contributors
# For license information, please see license.txt
# License: GNU Affero General Public License v3 or later (AGPLv3+)
# See https://www.gnu.org/licenses/agpl-3.0.html
```

## Domande?

- 💬 Apri una [Discussion su GitHub](https://github.com/Solede-SA/solede_openbanking/discussions)
- 📧 Email: info@solede.com
- 🐛 Segnala bug: [GitHub Issues](https://github.com/Solede-SA/solede_openbanking/issues)

## Grazie! 🙏

Ogni contributo, grande o piccolo, è apprezzato e aiuta a migliorare questo progetto per tutta la community!

---

Made with ❤️ by Solede SA and contributors
