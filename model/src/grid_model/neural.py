"""Optional CPU-compatible trained-from-scratch comparisons."""
import math
import torch
from torch import nn


class NeuralForecaster(nn.Module):
    def __init__(self, kind, inputs=11, hidden=64):
        super().__init__()
        self.kind = kind
        if kind == "lstm":
            self.encoder = nn.LSTM(inputs, hidden, batch_first=True)
        else:
            self.projection = nn.Linear(inputs, hidden)
            layer = nn.TransformerEncoderLayer(hidden, 4, hidden * 2, dropout=.1, batch_first=True)
            self.encoder = nn.TransformerEncoder(layer, 2)
            pos = torch.arange(4096).unsqueeze(1)
            div = torch.exp(torch.arange(0, hidden, 2) * (-math.log(10000.) / hidden))
            pe = torch.zeros(4096, hidden)
            pe[:, 0::2] = torch.sin(pos * div)
            pe[:, 1::2] = torch.cos(pos * div)
            self.register_buffer("position", pe)
        self.head = nn.Linear(hidden, 2)

    def forward(self, x):
        if self.kind == "lstm":
            x, _ = self.encoder(x)
        else:
            x = self.encoder(self.projection(x) + self.position[:x.shape[1]])
        return self.head(x[:, -1])


def train_neural(kind, train, val, seed=42, epochs=20, patience=3):
    import numpy as np
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    x = np.asarray([w[1] for w in train])
    y = np.asarray([w[2] for w in train], dtype=np.float32)
    mean, scale = x.mean((0, 1)), x.std((0, 1)).clip(.001)
    ym, ys = y.mean(0), y.std(0).clip(.001)
    tx = torch.tensor((x - mean) / scale)
    ty = torch.tensor((y - ym) / ys)
    vx = torch.tensor((np.asarray([w[1] for w in val]) - mean) / scale)
    vy = torch.tensor((np.asarray([w[2] for w in val], dtype=np.float32) - ym) / ys)
    net = NeuralForecaster(kind)
    optimizer = torch.optim.Adam(net.parameters(), lr=.001)
    best, stale, state = float("inf"), 0, None
    for epoch in range(epochs):
        net.train()
        for indices in torch.randperm(len(tx)).split(64):
            optimizer.zero_grad()
            loss = nn.functional.mse_loss(net(tx[indices]), ty[indices])
            loss.backward(); optimizer.step()
        net.eval()
        with torch.no_grad(): score = nn.functional.mse_loss(net(vx), vy).item()
        if score < best:
            best, stale = score, 0
            state = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            stale += 1
            if stale >= patience: break
    net.load_state_dict(state)
    return net, dict(mean=mean.tolist(), scale=scale.tolist(), y_mean=ym.tolist(), y_scale=ys.tolist(),
                     epochs_completed=epoch + 1, validation_loss=best)
