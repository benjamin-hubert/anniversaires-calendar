# 🎂 Anniversaires (chiffrés) → GitHub Pages → Home Assistant

Calendrier d'anniversaires généré à partir d'une simple liste JSON, publié en
`.ics` sur **GitHub Pages**. Les **prénoms sont chiffrés** (AES-256-GCM) : le
fichier public ne contient aucun nom en clair. Seul **Home Assistant**, avec la
clé secrète, déchiffre les prénoms. L'âge est calculé et inclus dans le titre
(chiffré lui aussi).

```
data/contacts.json ──> generate.py ──> public/anniversaires.ics ──> GitHub Pages
   (prénoms)          (chiffre avec        (titres chiffrés)            (public)
                       CALENDAR_KEY)                                       │
                                                                          ▼
                                              Home Assistant (pyscript) déchiffre
```

---

## 1. Générer la clé secrète (une seule fois)

```bash
python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Garde précieusement cette chaîne. Elle servira à **deux endroits identiques** :
le secret GitHub Actions, et `secrets.yaml` de Home Assistant. Sans elle, les
prénoms sont irrécupérables.

## 2. Mise en place GitHub (une seule fois)

1. Crée un dépôt (ex. `anniversaires-calendar`) et pousse ce dossier.
2. **Settings → Secrets and variables → Actions → New repository secret** :
   nom `CALENDAR_KEY`, valeur = la clé de l'étape 1.
3. **Settings → Pages → Source = GitHub Actions**.
4. Onglet **Actions** → workflow « Build & déployer le calendrier ICS » → **Run workflow**.
5. URL finale :
   ```
   https://<ton-pseudo>.github.io/anniversaires-calendar/anniversaires.ics
   ```

> Sans secret `CALENDAR_KEY`, le générateur produit un fichier **en clair** (utile
> pour tester localement). Avec le secret, tout est chiffré.

## 3. Gérer la liste — commande locale `manage.py`

```bash
python manage.py list                         # personnes actives
python manage.py list --all                   # inclut les ignorées
python manage.py add "Théo" 05/12/2018        # avec année  -> âge affiché
python manage.py add "Léa"  30/06             # sans année  -> sans âge
python manage.py add "Paul" 02/01/1990 --ref "Paul Durand"   # ref privé
python manage.py ignore "Romain Manicki"      # exclut (cible par ref si homonymes)
python manage.py unignore "Romain Manicki"    # réintègre
python manage.py remove "Paul Durand"         # supprime la fiche
```

- **`name`** = prénom affiché (jamais de nom de famille).
- **`ref`** = rappel privé pour distinguer les homonymes, jamais publié ni chiffré
  dans le calendrier (sert juste à la gestion locale et aux UID).
- **`ignore`** ajoute la personne à la liste `exclude` : elle reste dans le fichier
  mais n'apparaît plus dans le calendrier.

Après modif : `git commit` + `git push` → l'Action régénère et republie tout seul.

## 4. Home Assistant (pyscript)

1. Installe l'intégration **pyscript** (via HACS).
2. Copie `home-assistant/pyscript/anniversaires.py` dans `<config>/pyscript/`.
3. Dans `configuration.yaml` :
   ```yaml
   pyscript:
     allow_all_imports: true
     calendar_key: !secret calendar_key
     anniversaires_url: !secret anniversaires_url
   ```
4. Dans `secrets.yaml` :
   ```yaml
   calendar_key: "LA_MEME_CLE_QUE_LE_SECRET_GITHUB"
   anniversaires_url: "https://<ton-pseudo>.github.io/anniversaires-calendar/anniversaires.ics"
   ```
5. Redémarre HA. Un capteur **`sensor.anniversaires_a_venir`** apparaît :
   - état = nombre d'anniversaires dans les 30 jours,
   - attribut `events` = liste `[{date, in_days, label}]` avec les **prénoms déchiffrés**.
   Le service `pyscript.anniversaires_refresh` force une mise à jour ; sinon
   rafraîchissement automatique toutes les 6 h.

## 5. Fonctionnement / sécurité

- `generate.py` — une occurrence par personne et par année (fenêtre 80 ans), car
  l'ICS ne sait pas calculer l'âge. Le titre `Prénom (33 ans)` est chiffré en
  **AES-256-GCM déterministe** (nonce dérivé du texte → même entrée = même jeton,
  donc pas de réécriture inutile du fichier à chaque build).
- Ce qui reste **en clair** dans le fichier public : les **dates** des
  anniversaires (indispensable pour que ce soit un calendrier) et le nom du
  calendrier. Ce qui est **chiffré** : prénom + âge.
- La clé n'est jamais dans le dépôt (secret Actions + `secrets.yaml` HA).

### Lancer localement

```bash
pip install -r requirements.txt
export CALENDAR_KEY="ta_cle"      # omettre = sortie en clair
python generate.py                # -> public/anniversaires.ics
python generate.py --years 50     # fenêtre plus courte
```

## Note sur les données

La liste de départ provient des 46 contacts de l'app Contacts ayant une date de
naissance. 21 ont l'année (âge affiché), 25 n'ont que le jour/mois (sans âge).
`Benjamin Hubert` est pré-rempli dans `exclude` à titre d'exemple — ajuste avec
`manage.py`.
