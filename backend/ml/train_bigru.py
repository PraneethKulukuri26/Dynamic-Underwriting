"""
BiGRU Training Script
Full pipeline: data generation → preprocessing → train/val → model serialization.
"""

import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
from backend.ml.bigru_model import BiGRUBotDetector
from backend.ml.data_generator import generate_training_data


def train_bigru(
    epochs: int = 30,
    batch_size: int = 64,
    learning_rate: float = 0.001,
    n_human: int = 2000,
    n_bot: int = 1500,
    n_smart_bot: int = 500,
    seq_length: int = 200,
    save_path: str = "backend/ml/saved_models/bigru_bot_detector.pt",
):
    """Train the BiGRU bot detector model."""

    print("=" * 60)
    print("BiGRU Bot Detector - Training Pipeline")
    print("=" * 60)

    # Step 1: Generate data
    print(f"\n[1/5] Generating synthetic data: {n_human} human + {n_bot} bot + {n_smart_bot} smart-bot")
    sequences, labels = generate_training_data(n_human, n_bot, n_smart_bot, seq_length)
    print(f"  Dataset shape: {sequences.shape}, Labels: {labels.shape}")
    print(f"  Class distribution: Human={int((labels == 0).sum())}, Bot={int((labels == 1).sum())}")

    # Step 2: Train/Val split
    print("\n[2/5] Splitting train/val (80/20)")
    n_total = len(labels)
    n_train = int(0.8 * n_total)

    X_train = torch.FloatTensor(sequences[:n_train])
    y_train = torch.FloatTensor(labels[:n_train]).unsqueeze(1)
    X_val = torch.FloatTensor(sequences[n_train:])
    y_val = torch.FloatTensor(labels[n_train:]).unsqueeze(1)

    train_dataset = TensorDataset(X_train, y_train)
    val_dataset = TensorDataset(X_val, y_val)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    print(f"  Train: {len(train_dataset)}, Val: {len(val_dataset)}")

    # Step 3: Model setup
    print("\n[3/5] Initializing BiGRU model")
    model = BiGRUBotDetector()
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"  Parameters: {total_params:,}")

    # Step 4: Training loop
    print(f"\n[4/5] Training for {epochs} epochs")
    best_val_acc = 0.0

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            predicted = (outputs > 0.5).float()
            train_correct += (predicted == y_batch).sum().item()
            train_total += y_batch.size(0)

        # Validation
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)
                val_loss += loss.item()
                predicted = (outputs > 0.5).float()
                val_correct += (predicted == y_batch).sum().item()
                val_total += y_batch.size(0)

        train_acc = train_correct / max(train_total, 1)
        val_acc = val_correct / max(val_total, 1)
        avg_val_loss = val_loss / max(len(val_loader), 1)
        scheduler.step(avg_val_loss)

        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(
                f"  Epoch {epoch+1:3d}/{epochs}: "
                f"Train Loss={train_loss/len(train_loader):.4f}, Train Acc={train_acc:.4f} | "
                f"Val Loss={avg_val_loss:.4f}, Val Acc={val_acc:.4f}"
            )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_model_state = model.state_dict()

    # Step 5: Save model
    print(f"\n[5/5] Saving best model (Val Acc: {best_val_acc:.4f})")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    torch.save(best_model_state, save_path)
    print(f"  Model saved to: {save_path}")
    print("=" * 60)

    return best_val_acc


if __name__ == "__main__":
    train_bigru()
