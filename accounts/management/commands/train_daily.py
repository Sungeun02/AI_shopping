from __future__ import annotations

from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Train XGBoost model from CSV and write artifacts to ml_models/"

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        data_csv = base_dir / 'media' / 'datasets' / 'training_data.csv'
        model_out = base_dir / 'ml_models' / 'mart_recommender.xgb'
        scaler_out = base_dir / 'ml_models' / 'recommender_scaler.joblib'

        try:
            from train_models.train_model import train_from_csv
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Import failed: {e}"))
            return 1

        try:
            result = train_from_csv(data_csv, model_out, scaler_out)
        except Exception as e:
            self.stderr.write(self.style.ERROR(str(e)))
            return 1

        self.stdout.write(self.style.SUCCESS(
            f"OK: model={result['model_path']} scaler={result['scaler_path']} acc={result['accuracy']:.4f} rows={result['num_rows']} pos={result['num_positives']}"
        ))
        return 0




