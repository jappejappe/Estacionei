-- 1. Câmeras
CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    modelo VARCHAR(100), 
    ip_dispositivo VARCHAR(45), 
    localizacao TEXT, 
    ativa BOOLEAN DEFAULT TRUE 
);

-- 2. Vagas 
-- 0 = Livre, 1 = Ocupada 
CREATE TABLE IF NOT EXISTS vagas (
    id SERIAL PRIMARY KEY,
    codigo_vaga VARCHAR(50) UNIQUE NOT NULL, 
    latitude NUMERIC(10, 8) NOT NULL, 
    longitude NUMERIC(11, 8) NOT NULL, 
    status INTEGER DEFAULT 0, -- 0: Livre, 1: Ocupada
    ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
);

-- 3. Registros
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
    resultado_ia TEXT -- Armazena confiança e metadados do YOLOv8 [cite: 232]
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_vagas_status ON vagas(status);
CREATE INDEX IF NOT EXISTS idx_historico_vaga ON registros_historicos(vaga_id);