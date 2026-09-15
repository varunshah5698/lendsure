"""LendSure credit-risk ML v4 — real-data-anchored default prediction.

Data story (see metadata.json -> data_source after training):
  PRIMARY (real): UCI "Default of Credit Card Clients" (Yeh & Lien, 2009),
  30,000 Taiwan credit-card borrowers, 22.1% default rate, fetched from
  https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip
  AUGMENT (synthetic): 1,000,000 borrowers sampled from segment-conditional
  distributions FITTED on the real data (never hand-invented shapes), with
  labels drawn from a teacher model fitted on real data only.

Methodological honesty rules enforced by train.py:
  - Model SELECTION uses a held-out REAL validation split only.
  - Final reported metrics come from a held-out REAL test split the
    synthetic generator and the models never saw during fitting.
  - Nothing is rounded up, nothing is imputed silently: every mapping and
    assumption lives in features.py FEATURE_NOTES and metadata.json.
"""
