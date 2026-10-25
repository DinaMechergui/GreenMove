#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Création automatique du superutilisateur s'il est spécifié dans les variables d'environnement de Render
if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  echo "Création ou vérification du superutilisateur Django..."
  python manage.py createsuperuser --no-input || true
fi

# Initialisation des données de démo (points de trafic, récompenses, défis)
python manage.py seed_traffic_points || true
python manage.py seed_rewards || true
python manage.py seed_planner || true
