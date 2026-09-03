"""Sequence model for transaction patterns (Deep Learning stack: PyTorch).
Challenger to GBMs — weekly feature sequences -> LSTM -> default prob.
Guarded import: MVP runs without torch installed.
"""
try:
    import torch
    import torch.nn as nn
    TORCH_OK = True
except Exception:
    TORCH_OK = False


if TORCH_OK:
    class StressLSTM(nn.Module):
        """Weekly-aggregated sequence -> distress probability (2-4wk horizon)."""

        def __init__(self, n_features=25, hidden=64, layers=2):
            super().__init__()
            self.lstm = nn.LSTM(n_features, hidden, layers, batch_first=True)
            self.head = nn.Sequential(nn.Linear(hidden, 32), nn.ReLU(),
                                      nn.Linear(32, 1))

        def forward(self, x):
            _, (h, _) = self.lstm(x)
            return self.head(h[-1]).squeeze(-1)
else:
    class StressLSTM:  # stub so imports never break without torch
        def __init__(self, *a, **k):
            raise ImportError("torch not installed — pip install torch to enable sequence model")
