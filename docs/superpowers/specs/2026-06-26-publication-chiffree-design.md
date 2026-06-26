# Publication chiffrée — design

Date : 2026-06-26

## Contexte et problème

Le dépôt publie un calendrier d'anniversaires `.ics` sur GitHub Pages, avec les
titres (prénom + âge) chiffrés en AES-256-GCM. Pour des raisons de
confidentialité, `data/contacts.json` (prénoms et dates de naissance en clair) a
été retiré du versionnement **et de l'historique** git. En conséquence :

- Le fichier source n'est plus présent dans le checkout CI.
- Les déclencheurs automatiques du workflow `build.yml` sont désactivés
  (commentés) ; même un lancement manuel échouerait, faute de source de données.
- `public/anniversaires.ics` est gitignoré (déployé comme artefact Pages, jamais
  committé).

Résultat : un `git push` ne régénère plus le calendrier. Toute modification de la
liste (ex. mise à jour d'une date de naissance) reste purement locale.

## Objectif

Rétablir une chaîne de publication automatique **sans jamais exposer de données
personnelles en clair** dans le dépôt ou son historique : éditer la liste en
local, committer une forme chiffrée, pousser, et laisser l'Action régénérer et
déployer le `.ics`.

## Contrat de sortie (inchangé)

Le fichier publié reste un **ICS standard (RFC 5545)** :

- `SUMMARY: 🔒 <jeton>` où `<jeton>` = AES-256-GCM de `"Prénom (âge)"`
  (chiffrement déterministe, nonce dérivé par HMAC-SHA256 du texte clair).
- Les **dates** restent en clair (indispensable à un calendrier).
- Home Assistant déchiffre manuellement côté client via le module existant
  `home-assistant/pyscript/anniversaires.py` (déchiffrement inchangé).

Ce contrat est déjà satisfait par `generate.py` lorsque `CALENDAR_KEY` est défini.
Aucune modification du format de sortie ni du code Home Assistant.

## Architecture

```
Local (clair, gitignoré)            Dépôt (versionné)              CI / Pages
─────────────────────────           ──────────────────            ──────────────
data/contacts.json  ──manage.py──>  data/contacts.json.enc  ──>   generate.py
   (édition)          save()/seal      (blob chiffré)              load_contacts()
                                                                   déchiffre en mémoire
                                                                        │
                                                                        ▼
                                                          public/anniversaires.ics
                                                          (titres chiffrés, standard)
                                                                        │
                                                                        ▼
                                                                  GitHub Pages
```

### Composants

#### Module crypto partagé — `crypto_contacts.py` (nouveau)

Factorise la primitive pour éviter la duplication entre `generate.py` et
`manage.py`. Responsabilité unique : chiffrer/déchiffrer un blob de texte.

- `load_key() -> bytes | None` : lit `CALENDAR_KEY` (base64 → 32 octets), valide
  la longueur, renvoie `None` si absent. (Déplacement de la fonction existante de
  `generate.py`.)
- `encrypt_blob(key: bytes, plaintext: str) -> str` : AES-256-GCM, nonce dérivé
  par `HMAC-SHA256(key, plaintext)[:12]`, sortie `base64url(nonce + ct)`.
  Déterministe : même contenu → même blob → diffs git propres.
- `decrypt_blob(key: bytes, token: str) -> str` : inverse exact.

Le chiffrement des **titres** dans `generate.py` réutilise ces mêmes helpers
(`encrypt_label` devient un appel à `encrypt_blob`). Propriété de sécurité :
chaque message distinct a un nonce distinct (dérivé de son contenu) ; un même
message redonne le même couple nonce+ct (sûr, message identique). Pas de
réutilisation de nonce entre messages différents.

#### `manage.py` — scellage automatique

- `save(data)` :
  1. écrit `data/contacts.json` (clair local, comme aujourd'hui) ;
  2. si `CALENDAR_KEY` est présent dans l'environnement : (re)génère
     `data/contacts.json.enc` via `encrypt_blob` ;
  3. sinon : affiche un **avertissement** clair indiquant que le `.enc` n'a pas
     été régénéré (pour ne pas committer un `.enc` périmé sans le savoir).
- `load()` : lit `data/contacts.json` s'il existe ; sinon déchiffre
  `data/contacts.json.enc` avec la clé (bootstrap sur machine fraîche). Si ni le
  clair ni la clé ne sont disponibles : message d'erreur explicite.
- Conflit clair vs `.enc` : le clair local fait foi ; le prochain `save()` re-scelle.

#### `generate.py` — lecture de la source (Approche A)

- Nouvelle fonction `load_contacts(input_path) -> dict` :
  - si le fichier clair existe → le lire ;
  - sinon, si `<input>.enc` existe et `CALENDAR_KEY` est défini → déchiffrer en
    mémoire (`decrypt_blob`) et `json.loads` ;
  - sinon → erreur explicite (« ni clair ni .enc déchiffrable »).
- Aucun clair n'est écrit sur disque en CI.
- `--require-key` conserve son rôle (interdit de publier des prénoms en clair).

#### Workflow `build.yml` — réactivation

Décommenter les déclencheurs :

```yaml
on:
  push:
    branches: [ main ]
    paths:
      - "generate.py"
      - "crypto_contacts.py"
      - ".github/workflows/build.yml"
      - "data/contacts.json.enc"
  schedule:
    - cron: "0 2 * * *"   # garde la fenêtre d'âges fraîche
  workflow_dispatch:
```

Les étapes du job sont inchangées : `generate.py --require-key` lit le `.enc`
tout seul via `load_contacts()`.

### `.gitignore`

- `data/contacts.json` reste ignoré (clair, jamais versionné).
- `data/contacts.json.enc` est **versionné** sans modification du `.gitignore` :
  la règle `data/contacts.json` vise le chemin exact et n'attrape pas le suffixe
  `.enc` (vérifié via `git check-ignore`). On peut ajouter un commentaire dans le
  `.gitignore` pour rendre l'intention explicite, sans règle nécessaire.
- `public/` reste ignoré.

## Flux de données (cas nominal)

1. `export CALENDAR_KEY=…` en local.
2. `python manage.py add "Théo" 05/12/2018` → `save()` met à jour le clair **et**
   le `.enc`.
3. `git add data/contacts.json.enc && git commit && git push`.
4. L'Action se déclenche (push sur `data/contacts.json.enc`), `generate.py`
   déchiffre le `.enc` en mémoire, produit le `.ics` chiffré, déploie sur Pages.
5. Home Assistant rafraîchit et déchiffre les titres côté client.

## Gestion d'erreurs

- `CALENDAR_KEY` absent en CI → `--require-key` fait échouer le build (pas de
  publication en clair).
- `CALENDAR_KEY` absent en local lors d'un `save()` → clair mis à jour, `.enc`
  **non** régénéré, avertissement affiché.
- `.enc` illisible / mauvaise clé → `AESGCM` lève `InvalidTag` ; message d'erreur
  explicite, build en échec (pas de calendrier vide publié silencieusement).
- Ni clair ni `.enc` → erreur explicite dans `load_contacts()`.

## Tests

- **Round-trip blob** : `decrypt_blob(key, encrypt_blob(key, s)) == s`.
- **Déterminisme** : deux scellages du même contenu donnent un `.enc` identique.
- **Équivalence source** : `generate.py` depuis le `.enc` produit le même `.ics`
  que depuis le clair.
- **Scellage manage.py** : après une mutation (`add`), le `.enc` déchiffré reflète
  la modification.
- **Mauvaise clé** : `decrypt_blob` avec une clé erronée lève `InvalidTag`.
- **CI sans clé** : `generate.py --require-key` échoue proprement.

## Hors périmètre

- Aucun changement du format ICS publié ni du déchiffrement Home Assistant.
- Pas de rotation de clé automatisée (la clé reste un secret partagé manuel).
- Pas de chiffrement par champ : le blob entier est chiffré (le JSON complet est
  considéré comme donnée personnelle).
