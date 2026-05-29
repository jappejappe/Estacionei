-- Habilita extensões para cálculo de distância geográfica nativa no Postgres
CREATE EXTENSION IF NOT EXISTS cube;
CREATE EXTENSION IF NOT EXISTS earthdistance;

-- 1. Câmeras
CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    modelo VARCHAR(100), 
    ip_dispositivo VARCHAR(45), 
    localizacao TEXT, 
    ativa BOOLEAN DEFAULT TRUE 
);

-- 2. Vagas 
CREATE TABLE IF NOT EXISTS vagas (
    id SERIAL PRIMARY KEY,
    codigo_vaga VARCHAR(50) UNIQUE NOT NULL, 
    -- Mudado para DOUBLE PRECISION para casar perfeitamente com os cálculos matemáticos de GPS e o tipo float do Python
    latitude DOUBLE PRECISION NOT NULL, 
    longitude DOUBLE PRECISION NOT NULL, 
    status INTEGER DEFAULT 0, -- 0: Livre, 1: Ocupada
    ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
);

-- 3. Registros Históricos
CREATE TABLE IF NOT EXISTS registros_historicos (
    id SERIAL PRIMARY KEY,
    vaga_id INTEGER REFERENCES vagas(id) ON DELETE CASCADE, 
    status INTEGER NOT NULL,
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
);

-- 4. Logs de processamento (Auditoria da IA)
CREATE TABLE IF NOT EXISTS logs_processamento (
    id SERIAL PRIMARY KEY,
    camera_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL, 
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
    caminho_imagem VARCHAR(255), 
    resultado_ia TEXT 
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_vagas_status ON vagas(status);
CREATE INDEX IF NOT EXISTS idx_historico_vaga ON registros_historicos(vaga_id);
-- Índice espacial baseado em coordenadas para buscas ultra rápidas por proximidade
CREATE INDEX IF NOT EXISTS idx_vagas_coordenadas ON vagas USING gist (ll_to_earth(latitude, longitude));