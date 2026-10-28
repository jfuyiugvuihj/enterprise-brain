ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
    CONSTRAINT users_account_status CHECK (status IN ('active', 'disabled'));
