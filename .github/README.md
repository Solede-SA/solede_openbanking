# GitHub Workflows

This directory contains GitHub Actions workflows for automating various tasks.

## Workflows

### 🚀 Release (`release.yml`)

**Trigger:** Push di un tag `v*.*.*` (es. `v1.0.0`, `v1.2.3`)

**Cosa fa:**
1. Estrae automaticamente il changelog da `CHANGELOG.md` per la versione
2. Crea una GitHub Release con:
   - Nome del tag
   - Changelog della versione
   - Istruzioni di installazione
   - Note di licenza
   - Release notes generate automaticamente da commit
3. Pubblica la release pubblicamente

**Esempio uso:**
```bash
# Crea e pusha tag
git tag -a v1.1.0 -m "Release v1.1.0"
git push origin v1.1.0

# GitHub Actions crea automaticamente la release! 🎉
```

### 🔍 Lint (`lint.yml`)

**Trigger:** Pull request o push su branch `develop` o `main`

**Cosa fa:**
1. **Python:**
   - Linting con ruff
   - Controllo formattazione con ruff
2. **JavaScript:**
   - Linting con eslint
   - Controllo formattazione con prettier

**Esempio uso:**
```bash
# Quando fai push o apri PR, il workflow parte automaticamente
git push origin feature/new-feature

# Controlla risultati su GitHub Actions tab
```

## Permissions

I workflow richiedono questi permessi (già configurati):
- `contents: write` - Per creare release

## Secrets

Nessun secret custom necessario. Usa `GITHUB_TOKEN` automatico.

## Personalizzazione

### Modificare release.yml

Per cambiare il formato della release, modifica la sezione `body` in `release.yml`.

### Modificare lint.yml

Per aggiungere altri check, aggiungi step al job `lint-python` o `lint-javascript`.

## Troubleshooting

### Release non viene creata

1. Verifica che il tag segua il pattern `v*.*.*`
2. Controlla GitHub Actions tab per errori
3. Verifica permessi repository (Settings > Actions > General)

### Lint fallisce

1. Esegui localmente: `ruff check .` e `ruff format .`
2. Esegui pre-commit hooks: `pre-commit run --all-files`
3. Fixa gli errori e ri-pusha

---

Made with ❤️ by Solede SA
