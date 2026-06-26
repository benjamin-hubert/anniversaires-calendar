#!/usr/bin/env python3
"""
Gestion locale de la liste d'anniversaires (data/contacts.json).

Commandes :
    python manage.py list [--all]            Liste les personnes (--all inclut les ignorées)
    python manage.py add "Prénom" JJ/MM/AAAA [--ref "Prénom Nom"]
    python manage.py add "Prénom" JJ/MM       (année inconnue → sans âge)
    python manage.py ignore "Prénom|Nom"      Ajoute à la liste d'exclusion
    python manage.py unignore "Prénom|Nom"    Retire de la liste d'exclusion
    python manage.py remove "Prénom|Nom"      Supprime définitivement la fiche

Astuce : pour cibler une personne précise quand deux prénoms sont identiques,
utilise son "ref" (ex. "Romain Manicki") plutôt que le prénom seul.
"""

import argparse
import json
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data" / "contacts.json"


def load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def save(data):
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ids_of(person):
    """Identifiants reconnus pour cibler une personne : son name et son ref."""
    return {person["name"].strip().lower(),
            person.get("ref", person["name"]).strip().lower()}


def fmt_bd(bd: str) -> str:
    bd = bd.strip()
    if bd.startswith("--"):
        m, d = bd[2:].split("-")
        return f"{d}/{m} (sans année)"
    y, m, d = bd.split("-")
    return f"{d}/{m}/{y}"


def parse_date_arg(s: str) -> str:
    """Accepte JJ/MM/AAAA ou JJ/MM → renvoie le format interne stocké."""
    parts = s.replace("-", "/").split("/")
    if len(parts) == 3:
        d, m, y = (int(p) for p in parts)
        return f"{y:04d}-{m:02d}-{d:02d}"
    if len(parts) == 2:
        d, m = (int(p) for p in parts)
        return f"--{m:02d}-{d:02d}"
    raise SystemExit(f"Date invalide : {s!r} (attendu JJ/MM/AAAA ou JJ/MM)")


def cmd_list(data, args):
    exclude = {e.strip().lower() for e in data.get("exclude", [])}
    people = sorted(data["people"], key=lambda p: p["name"].lower())
    shown = 0
    print(f"{'':2} {'Prénom':<14} {'Réf.':<26} {'Anniversaire':<18} État")
    print("-" * 70)
    for p in people:
        ignored = bool(ids_of(p) & exclude)
        if ignored and not args.all:
            continue
        mark = "🚫" if ignored else "🎂"
        state = "ignoré" if ignored else "actif"
        print(f"{mark:2} {p['name']:<14} {p.get('ref',''):<26} "
              f"{fmt_bd(p['birthdate']):<18} {state}")
        shown += 1
    active = sum(1 for p in data["people"] if not (ids_of(p) & exclude))
    print("-" * 70)
    print(f"{active} actif(s), {len(data['people'])-active} ignoré(s), "
          f"{len(data['people'])} au total."
          + ("" if args.all else "  (utilise --all pour voir les ignorés)"))


def cmd_add(data, args):
    bd = parse_date_arg(args.date)
    person = {"name": args.name.strip(), "birthdate": bd}
    if args.ref:
        person["ref"] = args.ref.strip()
    data["people"].append(person)
    save(data)
    print(f"✅ Ajouté : {person['name']} — {fmt_bd(bd)}"
          + (f" (ref: {person['ref']})" if args.ref else ""))


def _match(data, target):
    t = target.strip().lower()
    hits = [p for p in data["people"] if t in ids_of(p)]
    return hits


def cmd_ignore(data, args):
    hits = _match(data, args.target)
    if not hits:
        raise SystemExit(f"Aucune personne ne correspond à {args.target!r}.")
    data.setdefault("exclude", [])
    # On exclut par le ref si dispo (plus précis), sinon par le name.
    added = []
    for p in hits:
        key = p.get("ref", p["name"])
        if key not in data["exclude"]:
            data["exclude"].append(key)
            added.append(key)
    save(data)
    print(f"🚫 Ignoré : {', '.join(added) if added else 'déjà ignoré'}")


def cmd_unignore(data, args):
    t = args.target.strip().lower()
    before = data.get("exclude", [])
    kept = [e for e in before if e.strip().lower() != t]
    # gère aussi le cas où on donne le prénom alors que le ref est exclu
    if len(kept) == len(before):
        refs = {p.get("ref", p["name"]) for p in _match(data, args.target)}
        kept = [e for e in before if e not in refs]
    removed = [e for e in before if e not in kept]
    data["exclude"] = kept
    save(data)
    print(f"✅ Réintégré : {', '.join(removed) if removed else 'rien à réintégrer'}")


def cmd_remove(data, args):
    t = args.target.strip().lower()
    keep = [p for p in data["people"] if t not in ids_of(p)]
    removed = len(data["people"]) - len(keep)
    if not removed:
        raise SystemExit(f"Aucune fiche ne correspond à {args.target!r}.")
    data["people"] = keep
    save(data)
    print(f"🗑️  Supprimé : {removed} fiche(s) correspondant à {args.target!r}")


def main():
    ap = argparse.ArgumentParser(description="Gestion de la liste d'anniversaires")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="Lister les personnes")
    p.add_argument("--all", action="store_true", help="Inclure les personnes ignorées")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("add", help="Ajouter une personne")
    p.add_argument("name", help="Prénom affiché")
    p.add_argument("date", help="JJ/MM/AAAA ou JJ/MM")
    p.add_argument("--ref", help="Rappel privé (ex. 'Prénom Nom'), jamais affiché")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("ignore", help="Ignorer une personne")
    p.add_argument("target", help="Prénom ou ref")
    p.set_defaults(func=cmd_ignore)

    p = sub.add_parser("unignore", help="Réintégrer une personne ignorée")
    p.add_argument("target", help="Prénom ou ref")
    p.set_defaults(func=cmd_unignore)

    p = sub.add_parser("remove", help="Supprimer définitivement une fiche")
    p.add_argument("target", help="Prénom ou ref")
    p.set_defaults(func=cmd_remove)

    args = ap.parse_args()
    data = load()
    args.func(data, args)


if __name__ == "__main__":
    main()
