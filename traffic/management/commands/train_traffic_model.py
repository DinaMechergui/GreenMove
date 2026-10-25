import json

from django.core.management.base import BaseCommand

from traffic.ml.train import train


class Command(BaseCommand):
    help = 'Entraîne le modèle de prédiction de congestion (LightGBM)'

    def add_arguments(self, parser):
        parser.add_argument('--test-days', type=int, default=10)

    def handle(self, *args, **opts):
        metrics = train(opts['test_days'])
        self.stdout.write(json.dumps(metrics, indent=2, ensure_ascii=False))
        self.stdout.write(self.style.SUCCESS('Modèle sauvegardé.'))