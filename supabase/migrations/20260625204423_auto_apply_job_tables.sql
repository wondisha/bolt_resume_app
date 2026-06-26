-- Applications table for tracking job applications
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL,
    reason TEXT,
    url TEXT,
    company_name TEXT,
    job_title TEXT,
    verified BOOLEAN DEFAULT FALSE,
    verification_source TEXT,
    score INTEGER,
    source TEXT DEFAULT 'runtime',
    artifacts JSONB DEFAULT '{}',
    gap_analysis JSONB,
    user_id UUID REFERENCES auth.users(id)
);

-- Question memory for reusable screening answers
CREATE TABLE IF NOT EXISTS question_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_question TEXT UNIQUE NOT NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id)
);

-- Enable RLS
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_memory ENABLE ROW LEVEL SECURITY;

-- RLS policies for authenticated users
CREATE POLICY "Users can view own applications" ON applications
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own applications" ON applications
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own applications" ON applications
    FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own applications" ON applications
    FOR DELETE TO authenticated USING (auth.uid() = user_id);

CREATE POLICY "Users can view own question memory" ON question_memory
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own question memory" ON question_memory
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own question memory" ON question_memory
    FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own question memory" ON question_memory
    FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- Policies for anonymous access (for single-user mode)
CREATE POLICY "Anon can view applications" ON applications
    FOR SELECT TO anon, authenticated USING (user_id IS NULL OR auth.uid() = user_id);

CREATE POLICY "Anon can insert applications" ON applications
    FOR INSERT TO anon, authenticated WITH CHECK (user_id IS NULL OR auth.uid() = user_id);

CREATE POLICY "Anon can view question memory" ON question_memory
    FOR SELECT TO anon, authenticated USING (user_id IS NULL OR auth.uid() = user_id);

CREATE POLICY "Anon can insert question memory" ON question_memory
    FOR INSERT TO anon, authenticated WITH CHECK (user_id IS NULL OR auth.uid() = user_id);

CREATE POLICY "Anon can update question memory" ON question_memory
    FOR UPDATE TO anon, authenticated USING (user_id IS NULL OR auth.uid() = user_id);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_applications_created_at ON applications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company_name);
CREATE INDEX IF NOT EXISTS idx_question_memory_normalized ON question_memory(normalized_question);