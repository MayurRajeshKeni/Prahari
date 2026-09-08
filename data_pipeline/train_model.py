"""
XGBoost Abuse Detection Model Trainer for Project Prahari
Trains a baseline classifier to detect bot/scraping/DDoS traffic from parsed web logs
and exports model artifacts (.json / .pkl) along with feature metadata for live gateway inference.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Tuple, List, Dict, Any

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix
import xgboost as xgb
import joblib

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    'status',
    'size',
    'hour',
    'url_depth',
    'has_query',
    'is_static',
    'ua_length',
    'is_bot_ua',
    'is_mobile_ua',
    'request_velocity',
    'requests_per_ip'
]


def load_and_prepare_data(csv_path: str) -> Tuple[pd.DataFrame, pd.Series]:
    logger.info(f"Loading dataset from {csv_path}")
    df = pd.read_csv(csv_path)

    # Determine ground-truth abuse label if not already present
    if 'is_bot' in df.columns:
        y = df['is_bot'].astype(int)
    else:
        # Heuristic labeling based on bot behavioral patterns
        bot_condition = (
            (df['is_bot_ua'] == 1) |
            ((df['request_velocity'] <= 0.5) & (df['requests_per_ip'] >= 30)) |
            (df['status'].isin([429, 403]) & (df['request_velocity'] <= 1.0))
        )
        y = bot_condition.astype(int)
        df['is_bot'] = y

    logger.info(f"Dataset summary: Total={len(df)}, Benign={sum(y == 0)} ({sum(y == 0)/len(df):.1%}), Bot/Abuse={sum(y == 1)} ({sum(y == 1)/len(df):.1%})")

    # Ensure all required features exist
    available_features = [col for col in FEATURE_COLUMNS if col in df.columns]
    missing_features = set(FEATURE_COLUMNS) - set(available_features)
    if missing_features:
        logger.warning(f"Missing expected features, creating defaults for: {missing_features}")
        for col in missing_features:
            df[col] = 0

    X = df[FEATURE_COLUMNS].copy()

    # Fill any remaining NaNs
    for col in FEATURE_COLUMNS:
        if X[col].isnull().any():
            X[col] = X[col].fillna(X[col].median())

    return X, y


def train_xgboost_model(X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame, y_test: pd.Series) -> xgb.XGBClassifier:
    logger.info("Training XGBoost Classifier...")
    
    # Calculate class weight ratio for scale_pos_weight
    neg_count = sum(y_train == 0)
    pos_count = sum(y_train == 1)
    scale_pos_weight = neg_count / max(pos_count, 1)

    model = xgb.XGBClassifier(
        n_estimators=150,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric='logloss',
        random_state=42
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_train, y_train), (X_test, y_test)],
        verbose=False
    )
    logger.info("Model training completed.")
    return model


def evaluate_model(model: xgb.XGBClassifier, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, Any]:
    logger.info("Evaluating model performance on test set...")
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    report = classification_report(y_test, y_pred, target_names=['Benign', 'Bot/Abuse'], output_dict=True)
    auc = roc_auc_score(y_test, y_prob)
    cm = confusion_matrix(y_test, y_pred)

    print("\n" + "="*50)
    print("           MODEL EVALUATION REPORT")
    print("="*50)
    print(classification_report(y_test, y_pred, target_names=['Benign', 'Bot/Abuse']))
    print(f"ROC-AUC Score: {auc:.4f}")
    print("\nConfusion Matrix:")
    print(f"  TN (Benign correctly identified): {cm[0][0]}")
    print(f"  FP (Benign falsely blocked):      {cm[0][1]}")
    print(f"  FN (Bot missed):                  {cm[1][0]}")
    print(f"  TP (Bot correctly caught):        {cm[1][1]}")

    print("\nFeature Importances:")
    importances = model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    for idx in sorted_idx:
        print(f"  - {FEATURE_COLUMNS[idx]:<20}: {importances[idx]:.4f}")
    print("="*50 + "\n")

    return {
        "roc_auc": float(auc),
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
        "feature_importances": {FEATURE_COLUMNS[i]: float(importances[i]) for i in sorted_idx}
    }


def export_artifacts(model: xgb.XGBClassifier, output_dir: str, metrics: Dict[str, Any]) -> None:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_model_path = out_path / "xgboost_abuse_model.json"
    pkl_model_path = out_path / "xgboost_abuse_model.pkl"
    metadata_path = out_path / "feature_metadata.json"
    metrics_path = out_path / "evaluation_metrics.json"

    # Save native XGBoost JSON
    model.save_model(str(json_model_path))
    logger.info(f"Saved native model to {json_model_path}")

    # Save pickle/joblib artifact
    joblib.dump(model, str(pkl_model_path))
    logger.info(f"Saved pickle model to {pkl_model_path}")

    # Save feature metadata for Phase 3 Gateway inference
    metadata = {
        "model_type": "XGBClassifier",
        "feature_columns": FEATURE_COLUMNS,
        "num_features": len(FEATURE_COLUMNS),
        "target_classes": {0: "Benign", 1: "Bot/Abuse"},
        "threshold": 0.5
    }
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Saved feature metadata to {metadata_path}")

    # Save evaluation metrics
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"Saved metrics to {metrics_path}")


def main(data_path: str, output_dir: str, test_size: float = 0.2) -> None:
    X, y = load_and_prepare_data(data_path)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )
    logger.info(f"Split data: Train={len(X_train)} samples, Test={len(X_test)} samples")

    model = train_xgboost_model(X_train, y_train, X_test, y_test)
    metrics = evaluate_model(model, X_test, y_test)
    export_artifacts(model, output_dir, metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train XGBoost Abuse Detection Model for Prahari")
    parser.add_argument("data", help="Path to processed CSV dataset")
    parser.add_argument("--output-dir", default="models", help="Directory to save model artifacts")
    parser.add_argument("--test-size", type=float, default=0.2, help="Validation test split ratio")

    args = parser.parse_args()
    main(args.data, args.output_dir, args.test_size)
