-- LEIA ISSO TUDO ANTES DE USAR(AS 2000 LINHAS(SO OS COMENTÁRIOS) SÃO IMPORTANTES PARA ENTENDER O BANCO DE DADOS):
-- =====================================================================
-- SAM - Simple Automotive Maintenance
-- init.sql - Inicialização completa do banco de dados (PostgreSQL 13+)
--
-- Convenções:
--   * Identificadores em inglês; comentários e mensagens de erro em português.
--   * Execução atômica: tudo roda em uma única transação (BEGIN ... COMMIT).
--   * Senhas: somente hashes (bcrypt/argon2 etc.) gerados pelo backend.
--   * Exclusões: CASCADE apenas para dados "pertencentes" a outro registro
--     (página da oficina, horários, favoritos, chat, notificações). Registros
--     com valor histórico/financeiro (atendimentos, orçamentos e seus itens,
--     avaliações, manutenções, peças utilizadas, divulgações, denúncias) usam
--     RESTRICT/NO ACTION: desative-os por status em vez de apagá-los. O mesmo
--     vale para serviços e produtos do catálogo da oficina já usados em
--     orçamentos: desative-os (disponibility/active) em vez de excluí-los.
--   * Tempo: validades de orçamento/promoção/divulgação usam NOW() (início da
--     transação) e intervalo semiaberto [início, fim): no instante exato de
--     date_validity / date_end o registro JÁ está vencido.
--   * Expiração: o banco não executa nada sozinho com a passagem do tempo.
--     Agende run_expiration_jobs() (seção 9.11) a cada 1-5 minutos no backend,
--     no cron do sistema ou, opcionalmente, com pg_cron (nunca obrigatório).
--   -- Concorrência:
--   * READ COMMITTED é o nível de isolamento padrão.
--   * Deadlocks (40P01) podem ocorrer em qualquer nível de isolamento
--     quando transações bloqueiam recursos em ordens incompatíveis.
--   * O PostgreSQL aborta uma das transações envolvidas.
--   * O backend deverá repetir a transação inteira em caso de 40P01
--     e tratar 40001 conforme a política de transações.
-- =====================================================================

BEGIN;

DO $$
BEGIN
    IF current_setting('server_version_num')::INT < 130000 THEN
        RAISE EXCEPTION 'O SAM requer PostgreSQL 13 ou superior (versão atual: %).',
            current_setting('server_version');
    END IF;
END $$;

-- =====================================================================
-- 1. TIPOS ENUMERADOS
-- =====================================================================

CREATE TYPE FUEL AS ENUM (
    'gasolina',
    'etanol',
    'diesel',
    'flex',
    'eletrico',
    'hibrido',
    'gnv',
    'outro'
);

CREATE TYPE EXCHANGE AS ENUM (
    'manual',
    'automatico',
    'automatizado',
    'dupla_embreagem',
    'variavel',
    'outro'
);

CREATE TYPE TYPE_ESTABLISHMENT AS ENUM (
    'oficina',
    'borracharia',
    'posto_combustivel',
    'loja_autopecas',
    'centro_automotivo',
    'concessionaria',
    'lava_jato',
    'outro'
);

CREATE TYPE STATUS_ATTENDANCE AS ENUM (
    'requested',
    'budgeted',
    'waiting_approval',
    'approved',
    'in_progress',
    'completed',
    'delivered',
    'canceled'
);

-- =====================================================================
-- 2. CLIENT, POINT_OF_INTEREST, WORKSHOP, PAG_WORKSHOP, VEHICLE
-- =====================================================================

CREATE TABLE CLIENT (
    id_client BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,      -- apenas hash seguro, nunca senha em texto puro
    phone_number VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    photo_profile VARCHAR(500),               -- caminho/URL do arquivo, nunca o binário

    CONSTRAINT ck_client_status CHECK (status IN ('active', 'inactive', 'blocked')),
    CONSTRAINT ck_client_email CHECK (POSITION('@' IN email) > 1)
);

-- Unicidade de e-mail sem diferenciar maiúsculas/minúsculas
CREATE UNIQUE INDEX uq_client_email ON CLIENT (LOWER(email));

-- Pontos do mapa: podem existir sem oficina cadastrada (dados de fontes externas)
CREATE TABLE POINT_OF_INTEREST (
    id_point_of_interest BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type TYPE_ESTABLISHMENT NOT NULL,
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    address TEXT,
    -- Origem externa (opcional). Armazene somente o que os termos de uso da
    -- fonte permitirem (em geral, o identificador do estabelecimento).
    external_source VARCHAR(50),
    external_id VARCHAR(255),

    CONSTRAINT ck_poi_latitude CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT ck_poi_longitude CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT ck_poi_external CHECK ((external_source IS NULL) = (external_id IS NULL)),
    CONSTRAINT uq_poi_external UNIQUE (external_source, external_id)
);

CREATE INDEX idx_poi_coordinates ON POINT_OF_INTEREST (latitude, longitude);

CREATE TABLE WORKSHOP (
    id_workshop BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name_fantasy VARCHAR(255) NOT NULL,
    name_responsible VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,      -- apenas hash seguro
    phone_number VARCHAR(255),
    cnpj VARCHAR(14) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    -- Associação 1:1 e opcional com o ponto do mapa. Escolhida/confirmada pelo
    -- responsável no cadastro; NUNCA criada automaticamente por proximidade.
    -- UNIQUE: um ponto não pode ser reivindicado por duas oficinas.
    id_point_of_interest BIGINT UNIQUE
        REFERENCES POINT_OF_INTEREST (id_point_of_interest) ON DELETE SET NULL,

    CONSTRAINT ck_workshop_status CHECK (status IN ('active', 'inactive', 'blocked')),
    CONSTRAINT ck_workshop_cnpj CHECK (cnpj ~ '^[0-9]{14}$'),  -- somente dígitos
    CONSTRAINT ck_workshop_email CHECK (POSITION('@' IN email) > 1)
);

CREATE UNIQUE INDEX uq_workshop_email ON WORKSHOP (LOWER(email));

-- Uma página pública por oficina
CREATE TABLE PAG_WORKSHOP (
    id_pag_workshop BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_workshop BIGINT NOT NULL UNIQUE REFERENCES WORKSHOP (id_workshop) ON DELETE CASCADE,
    description TEXT,
    photo_profile VARCHAR(500) DEFAULT 'default-profile.png',
    photo_banner VARCHAR(500)
);

CREATE TABLE VEHICLE (
    id_vehicle BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_client BIGINT NOT NULL REFERENCES CLIENT (id_client) ON DELETE CASCADE,
    brand VARCHAR(255) NOT NULL,
    model VARCHAR(255) NOT NULL,
    year_fabrication INT NOT NULL,
    year_model INT NOT NULL,
    plate VARCHAR(7) NOT NULL,                -- texto; maiúsculas, sem hífen
    fuel FUEL NOT NULL,
    exchange EXCHANGE NOT NULL,
    version VARCHAR(255),
    motorization VARCHAR(255),
    color VARCHAR(20),
    information TEXT,
    photo_1 VARCHAR(500),
    photo_2 VARCHAR(500),
    photo_3 VARCHAR(500),

    -- O mesmo cliente não cadastra a mesma placa duas vezes. Não prova propriedade.
    CONSTRAINT unique_vehicle UNIQUE (id_client, plate),
    -- Necessária para a FK composta de ATTENDANCE (veículo pertence ao cliente)
    CONSTRAINT uq_vehicle_id_client UNIQUE (id_vehicle, id_client),
    -- Formato antigo (AAA9999) e Mercosul (AAA9A99)
    CONSTRAINT ck_vehicle_plate CHECK (plate ~ '^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$'),
    CONSTRAINT ck_vehicle_year_fabrication CHECK (year_fabrication BETWEEN 1900 AND 2100),
    CONSTRAINT ck_vehicle_year_model CHECK (year_model BETWEEN 1900 AND 2100)
);

-- =====================================================================
-- 3. OPERATION_HOUR (vários intervalos por dia; sem sobreposição)
-- =====================================================================

CREATE TABLE OPERATION_HOUR (
    id_operation_hour BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_workshop BIGINT NOT NULL REFERENCES WORKSHOP (id_workshop) ON DELETE CASCADE,
    day_of_week INT NOT NULL,                 -- ISO-8601: 1 = segunda ... 7 = domingo
    opening_time TIME NOT NULL,
    closing_time TIME NOT NULL,

    CONSTRAINT ck_operation_hour_day CHECK (day_of_week BETWEEN 1 AND 7),
    CONSTRAINT ck_operation_hour_interval CHECK (closing_time > opening_time)
);

CREATE INDEX idx_operation_hour_workshop_day ON OPERATION_HOUR (id_workshop, day_of_week);

-- =====================================================================
-- 4. SERVICE_CATEGORY, SERVICE (catálogo global), WORKSHOP_SERVICE, PRODUCT
-- =====================================================================

CREATE TABLE SERVICE_CATEGORY (
    id_service_category BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT
);

INSERT INTO SERVICE_CATEGORY (name) VALUES
    ('Manutenção'),
    ('Estética'),
    ('Acessórios'),
    ('Ar-condicionado'),
    ('Diagnóstico'),
    ('Elétrica'),
    ('Motor'),
    ('Transmissão'),
    ('Pneus'),
    ('Funilaria e pintura'),
    ('Inspeção');

-- Regra ÚNICA de normalização de nomes de serviço. É usada pelo índice de
-- unicidade de SERVICE, pelo de WORKSHOP_SERVICE e por
-- approve_workshop_service_request(), de modo que a comparação seja idêntica
-- em todos os pontos:
--   * clean_service_name      : colapsa qualquer sequência de espaços/tabs/quebras
--                               em um único espaço e remove espaços das pontas
--                               (preserva maiúsculas/minúsculas; é o nome exibido);
--   * normalize_service_name  : clean_service_name em minúsculas (chave de unicidade).
-- Compara TEXTO, não significado: não remove acentos nem funde nomes apenas
-- parecidos ("Troca de óleo" e "Troca de oleo" continuam sendo serviços distintos).
--
-- normalize_service_name() chama clean_service_name() COM o schema (P-21): os
-- índices por expressão abaixo a executam com search_path restrito — CREATE INDEX
-- e REINDEX no PostgreSQL 17+ (pg_catalog, pg_temp) e o pg_restore (search_path
-- vazio). Sem o "public." a função não é encontrada e o init.sql não aplica.
CREATE OR REPLACE FUNCTION clean_service_name(p_name TEXT)
RETURNS TEXT AS $$
    SELECT BTRIM(REGEXP_REPLACE(p_name, '\s+', ' ', 'g'));
$$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE;

CREATE OR REPLACE FUNCTION normalize_service_name(p_name TEXT)
RETURNS TEXT AS $$
    SELECT LOWER(public.clean_service_name(p_name));
$$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE;

CREATE TABLE SERVICE (
    id_service BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    id_category BIGINT NOT NULL REFERENCES SERVICE_CATEGORY (id_service_category),
    active BOOLEAN NOT NULL DEFAULT TRUE,

    -- O nome armazenado é sempre o nome "limpo" (sem espaços sobrando)
    CONSTRAINT ck_service_name_clean CHECK (name <> '' AND name = clean_service_name(name))
);

-- Unicidade do catálogo global por nome normalizado (substitui o UNIQUE(name),
-- que só detectava nomes idênticos byte a byte e é implicado por este índice).
-- Também é o alvo do ON CONFLICT de approve_workshop_service_request().
CREATE UNIQUE INDEX uq_service_name_normalized ON SERVICE (normalize_service_name(name));
CREATE INDEX idx_service_category ON SERVICE (id_category);

-- Catálogo inicial. A categoria é resolvida pelo NOME (não por IDs numéricos),
-- então uma categoria inexistente gera erro (id_category NOT NULL) em vez de
-- associação silenciosamente errada.
INSERT INTO SERVICE (name, description, id_category)
SELECT v.name, v.description, c.id_service_category
FROM (VALUES
    ('Troca de óleo', 'Serviço de troca de óleo do motor', 'Manutenção'),
    ('Alinhamento e balanceamento', 'Serviço de alinhamento e balanceamento das rodas', 'Pneus'),
    ('Revisão completa', 'Serviço de revisão completa do veículo', 'Manutenção'),
    ('Troca de pneus', 'Serviço de troca de pneus do veículo', 'Pneus'),
    ('Lavagem e estética automotiva', 'Serviço de lavagem e estética automotiva', 'Estética'),
    ('Troca de bateria', 'Serviço de troca da bateria do veículo', 'Elétrica'),
    ('Troca de pastilhas de freio', 'Serviço de troca das pastilhas de freio do veículo', 'Manutenção'),
    ('Troca de correia dentada', 'Serviço de troca da correia dentada do veículo', 'Motor'),
    ('Troca de amortecedores', 'Serviço de troca dos amortecedores do veículo', 'Manutenção'),
    ('Troca de velas de ignição', 'Serviço de troca das velas de ignição do veículo', 'Motor'),
    ('Troca de filtros', 'Serviço de troca dos filtros do veículo', 'Manutenção'),
    ('Troca de fluidos', 'Serviço de troca dos fluidos do veículo', 'Manutenção'),
    ('Troca de embreagem', 'Serviço de troca da embreagem do veículo', 'Transmissão'),
    ('Troca de suspensão', 'Serviço de troca da suspensão do veículo', 'Manutenção'),
    ('Troca de escapamento', 'Serviço de troca do escapamento do veículo', 'Manutenção'),
    ('Troca de faróis e lanternas', 'Serviço de troca dos faróis e lanternas do veículo', 'Elétrica'),
    ('Troca de retrovisores', 'Serviço de troca dos retrovisores do veículo', 'Manutenção'),
    ('Troca de para-brisa e vidros', 'Serviço de troca do para-brisa e vidros do veículo', 'Manutenção'),
    ('Troca de acessórios automotivos', 'Serviço de troca dos acessórios automotivos do veículo', 'Acessórios'),
    ('Instalação de som automotivo', 'Serviço de instalação de som automotivo no veículo', 'Acessórios'),
    ('Instalação de alarme automotivo', 'Serviço de instalação de sistema de alarme no veículo', 'Acessórios'),
    ('Instalação de câmera de ré', 'Serviço de instalação de câmera para auxiliar em manobras', 'Acessórios'),
    ('Instalação de sensores de estacionamento', 'Serviço de instalação de sensores para auxiliar em manobras', 'Acessórios'),
    ('Instalação de rastreador veicular', 'Serviço de instalação de dispositivo de rastreamento veicular', 'Acessórios'),
    ('Instalação de engate', 'Serviço de instalação de engate para reboque', 'Acessórios'),
    ('Instalação de película automotiva', 'Serviço de aplicação de películas nos vidros do veículo', 'Estética'),
    ('Polimento automotivo', 'Serviço de polimento da pintura do veículo', 'Estética'),
    ('Higienização interna', 'Serviço de limpeza e higienização do interior do veículo', 'Estética'),
    ('Higienização de ar-condicionado', 'Serviço de limpeza e higienização do sistema de ar-condicionado', 'Ar-condicionado'),
    ('Manutenção de ar-condicionado', 'Serviço de diagnóstico e reparo do sistema de ar-condicionado', 'Ar-condicionado'),
    ('Recarga de gás do ar-condicionado', 'Serviço de recarga do fluido refrigerante do sistema de ar-condicionado', 'Ar-condicionado'),
    ('Diagnóstico eletrônico', 'Serviço de identificação de falhas nos sistemas eletrônicos do veículo', 'Diagnóstico'),
    ('Diagnóstico de motor', 'Serviço de identificação de falhas no motor do veículo', 'Diagnóstico'),
    ('Diagnóstico de transmissão', 'Serviço de identificação de falhas na transmissão do veículo', 'Diagnóstico'),
    ('Diagnóstico de freios', 'Serviço de identificação de falhas no sistema de freios do veículo', 'Diagnóstico'),
    ('Reparo elétrico automotivo', 'Serviço de diagnóstico e reparo dos sistemas elétricos do veículo', 'Elétrica'),
    ('Reparo do alternador', 'Serviço de diagnóstico e reparo do alternador', 'Elétrica'),
    ('Reparo do motor de partida', 'Serviço de diagnóstico e reparo do motor de partida', 'Elétrica'),
    ('Manutenção da injeção eletrônica', 'Serviço de diagnóstico e manutenção do sistema de injeção eletrônica', 'Motor'),
    ('Limpeza de bicos injetores', 'Serviço de limpeza dos bicos injetores do motor', 'Motor'),
    ('Manutenção do sistema de arrefecimento', 'Serviço de inspeção e manutenção do sistema de arrefecimento do motor', 'Motor'),
    ('Troca de radiador', 'Serviço de substituição do radiador do veículo', 'Motor'),
    ('Troca da bomba de água', 'Serviço de substituição da bomba de água do sistema de arrefecimento', 'Motor'),
    ('Retífica de motor', 'Serviço de recuperação e retífica de componentes do motor', 'Motor'),
    ('Reparo de motor', 'Serviço de diagnóstico e reparo do motor do veículo', 'Motor'),
    ('Reparo de câmbio', 'Serviço de diagnóstico e reparo do sistema de transmissão', 'Transmissão'),
    ('Troca de óleo do câmbio', 'Serviço de substituição do fluido da transmissão', 'Transmissão'),
    ('Manutenção do sistema de freios', 'Serviço de inspeção e manutenção do sistema de freios', 'Manutenção'),
    ('Sangria do sistema de freios', 'Serviço de remoção de ar do circuito hidráulico dos freios', 'Manutenção'),
    ('Reparo da direção hidráulica', 'Serviço de diagnóstico e reparo do sistema de direção hidráulica', 'Manutenção'),
    ('Conserto de pneus', 'Serviço de reparo de pneus danificados', 'Pneus'),
    ('Vulcanização de pneus', 'Serviço de reparo de pneus por meio de vulcanização', 'Pneus'),
    ('Calibragem de pneus', 'Serviço de ajuste da pressão dos pneus', 'Pneus'),
    ('Reparo de para-choque', 'Serviço de recuperação e reparo de para-choques', 'Funilaria e pintura'),
    ('Pintura automotiva', 'Serviço de pintura de partes ou da carroceria do veículo', 'Funilaria e pintura'),
    ('Funilaria automotiva', 'Serviço de recuperação de partes danificadas da carroceria', 'Funilaria e pintura'),
    ('Martelinho de ouro', 'Serviço de remoção de pequenos amassados na carroceria', 'Funilaria e pintura'),
    ('Restauração de faróis', 'Serviço de recuperação e polimento das lentes dos faróis', 'Estética'),
    ('Revisão preventiva', 'Serviço de inspeção preventiva dos principais sistemas do veículo', 'Manutenção'),
    ('Inspeção pré-compra', 'Serviço de avaliação das condições mecânicas e estruturais de um veículo antes da compra', 'Inspeção'),
    ('Revisão pré-viagem', 'Serviço de verificação dos sistemas do veículo antes de uma viagem', 'Inspeção'),
    ('Instalação de acessórios automotivos', 'Serviço de instalação de acessórios adicionais no veículo', 'Acessórios')
) AS v (name, description, category)
LEFT JOIN SERVICE_CATEGORY c ON c.name = v.category;

-- Serviços oferecidos por cada oficina.
--   * Seleção do catálogo global: id_service preenchido e status_solicitation NULL.
--   * Serviço personalizado: name_local obrigatório; fica disponível de imediato
--     no catálogo da oficina e nasce com status_solicitation = 'pending'
--     (= solicitação de inclusão no catálogo global).
--       - aprovado : id_service passa a apontar para o SERVICE global ('approved')
--       - rejeitado: permanece só no catálogo da oficina ('rejected' + motivo)
--     (ver approve_/reject_workshop_service_request mais abaixo)
CREATE TABLE WORKSHOP_SERVICE (
    id_workshop_service BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_workshop BIGINT NOT NULL REFERENCES WORKSHOP (id_workshop) ON DELETE CASCADE,
    id_service BIGINT REFERENCES SERVICE (id_service),
    name_local VARCHAR(255),
    description_local TEXT,
    id_suggested_category BIGINT
        REFERENCES SERVICE_CATEGORY (id_service_category) ON DELETE SET NULL,
    price_base DECIMAL(10, 2) NOT NULL CHECK (price_base >= 0),
    duration_estimate INT NOT NULL CHECK (duration_estimate > 0),  -- em minutos
    disponibility BOOLEAN NOT NULL DEFAULT TRUE,
    status_solicitation VARCHAR(50),
    motivation_rejection TEXT,
    date_solicitation_response TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_ws_status CHECK (
        status_solicitation IS NULL
        OR status_solicitation IN ('pending', 'approved', 'rejected')
    ),
    CONSTRAINT ck_ws_origin CHECK (
        -- seleção do catálogo global
        (status_solicitation IS NULL AND id_service IS NOT NULL)
        -- serviço personalizado
        OR (status_solicitation IS NOT NULL
            AND name_local IS NOT NULL
            AND ((status_solicitation IN ('pending', 'rejected') AND id_service IS NULL)
                 OR (status_solicitation = 'approved' AND id_service IS NOT NULL)))
    ),
    CONSTRAINT ck_ws_rejection CHECK (
        COALESCE(status_solicitation = 'rejected', FALSE) = (motivation_rejection IS NOT NULL)
    ),
    CONSTRAINT uq_ws_workshop_service UNIQUE (id_workshop, id_service),
    -- Necessária para as FKs compostas (garantem que o serviço é da mesma oficina)
    CONSTRAINT uq_ws_id_workshop UNIQUE (id_workshop_service, id_workshop),
    CONSTRAINT ck_ws_name_local_clean
    CHECK (
        name_local IS NULL
        OR (
            name_local <> ''
            AND name_local = clean_service_name(name_local)
        )
    )
);

CREATE UNIQUE INDEX uq_ws_custom_name
    ON WORKSHOP_SERVICE (id_workshop, normalize_service_name(name_local))
    WHERE name_local IS NOT NULL AND status_solicitation IS NOT NULL;
CREATE INDEX idx_ws_service ON WORKSHOP_SERVICE (id_service);
CREATE INDEX idx_ws_pending ON WORKSHOP_SERVICE (created_at) WHERE status_solicitation = 'pending';

CREATE TABLE PRODUCT (
    id_product BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_workshop BIGINT NOT NULL REFERENCES WORKSHOP (id_workshop) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(255),
    brand VARCHAR(255),
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    disponibility BOOLEAN NOT NULL DEFAULT TRUE,
    photo VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT uq_product_id_workshop UNIQUE (id_product, id_workshop)
);

CREATE INDEX idx_product_workshop ON PRODUCT (id_workshop);

-- =====================================================================
-- 5. ATTENDANCE, BUDGET, BUDGET_ITEM
-- =====================================================================

CREATE TABLE ATTENDANCE (
    id_attendance BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_client BIGINT NOT NULL REFERENCES CLIENT (id_client) ON DELETE RESTRICT,
    id_vehicle BIGINT NOT NULL,
    id_workshop BIGINT NOT NULL REFERENCES WORKSHOP (id_workshop) ON DELETE RESTRICT,
    date_attendance TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status_attendance STATUS_ATTENDANCE NOT NULL DEFAULT 'requested',
    mileage_km INT CHECK (mileage_km >= 0),   -- quilometragem do veículo no atendimento
    observations TEXT,

    -- O veículo precisa pertencer ao cliente do atendimento
    CONSTRAINT fk_attendance_vehicle_client
        FOREIGN KEY (id_vehicle, id_client)
        REFERENCES VEHICLE (id_vehicle, id_client) ON DELETE RESTRICT,
    CONSTRAINT uq_attendance_id_workshop UNIQUE (id_attendance, id_workshop),
    CONSTRAINT uq_attendance_id_vehicle UNIQUE (id_attendance, id_vehicle)
);

CREATE INDEX idx_attendance_client ON ATTENDANCE (id_client);
CREATE INDEX idx_attendance_vehicle ON ATTENDANCE (id_vehicle);
CREATE INDEX idx_attendance_workshop_status ON ATTENDANCE (id_workshop, status_attendance);

-- Orçamento: controla o ciclo de vida COMERCIAL da proposta.
-- O atendimento controla a EXECUÇÃO. A sincronização entre ambos é feita por
-- triggers (seção 8), de modo que uma transição nunca dependa de estados
-- incompatíveis.
CREATE TABLE BUDGET (
    id_budget BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_attendance BIGINT NOT NULL,
    id_workshop BIGINT NOT NULL,              -- preenchido automaticamente a partir do atendimento
    date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_validity TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '7 days'),
    total_price DECIMAL(12, 2) NOT NULL DEFAULT 0 CHECK (total_price >= 0),  -- mantido por trigger
    status_budget VARCHAR(50) NOT NULL DEFAULT 'pending',
    date_response TIMESTAMPTZ,                -- NULL enquanto não houver resposta
    observations TEXT,

    CONSTRAINT ck_budget_status CHECK (status_budget IN (
        'pending', 'approved', 'rejected', 'cancelled', 'expired'
    )),
    CONSTRAINT ck_budget_validity CHECK (date_validity > date_creation),
    CONSTRAINT ck_budget_response CHECK (
        (status_budget = 'pending' AND date_response IS NULL)
        OR (status_budget IN ('approved', 'rejected') AND date_response IS NOT NULL)
        OR status_budget IN ('cancelled', 'expired')
    ),
    CONSTRAINT fk_budget_attendance
        FOREIGN KEY (id_attendance, id_workshop)
        REFERENCES ATTENDANCE (id_attendance, id_workshop) ON DELETE RESTRICT,
    CONSTRAINT uq_budget_id_workshop UNIQUE (id_budget, id_workshop),
    CONSTRAINT uq_budget_id_attendance UNIQUE (id_budget, id_attendance)
);

CREATE INDEX idx_budget_attendance ON BUDGET (id_attendance);
-- Apoia expire_pending_budgets(): varre só orçamentos pendentes, por validade
CREATE INDEX idx_budget_pending_validity ON BUDGET (date_validity) WHERE status_budget = 'pending';
-- No máximo uma proposta em aberto e uma aprovada por atendimento
CREATE UNIQUE INDEX uq_budget_one_pending
    ON BUDGET (id_attendance) WHERE status_budget = 'pending';
CREATE UNIQUE INDEX uq_budget_one_approved
    ON BUDGET (id_attendance) WHERE status_budget = 'approved';

-- Itens do orçamento: ÚNICO local onde serviços, produtos/peças, mão de obra e
-- outros valores cobrados são registrados (não há tabela de serviços por
-- atendimento). Descrição, quantidade e preço são um "retrato" (snapshot) da
-- proposta: alterações posteriores no catálogo não modificam orçamentos antigos.
--   * service     : exige id_workshop_service (serviço da MESMA oficina), sem produto;
--   * product     : exige id_product (produto da MESMA oficina), sem serviço;
--   * labor/other : sem referência de catálogo.
-- As FKs de catálogo são RESTRICT: serviço/produto já orçado não pode ser
-- excluído (desative-o); o histórico também fica preservado pelo retrato textual.
-- A FK para o orçamento é RESTRICT: excluir um orçamento nunca apaga seus itens
-- em cascata (itens só são removidos, um a um, de orçamento pendente).
CREATE TABLE BUDGET_ITEM (
    id_budget_item BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_budget BIGINT NOT NULL,
    id_workshop BIGINT NOT NULL,              -- preenchido automaticamente a partir do orçamento
    item_type VARCHAR(20) NOT NULL,
    id_workshop_service BIGINT,               -- obrigatório para 'service' (ver ck_bi_reference)
    id_product BIGINT,                        -- obrigatório para 'product' (ver ck_bi_reference)
    -- Opcional, só para produto/peça: item de SERVIÇO DO MESMO ORÇAMENTO ao qual a
    -- peça pertence (ex.: filtro usado na "Troca de óleo"). A coluna gerada
    -- service_item_type permite validar, só com FK, que o alvo é um serviço.
    id_service_item BIGINT,
    service_item_type VARCHAR(20)
        GENERATED ALWAYS AS (CASE WHEN id_service_item IS NOT NULL THEN 'service' END) STORED,
    description VARCHAR(255) NOT NULL,
    quantity DECIMAL(10, 3) NOT NULL DEFAULT 1,
    unit_price DECIMAL(10, 2) NOT NULL,
    subtotal DECIMAL(12, 2) GENERATED ALWAYS AS (ROUND(quantity * unit_price, 2)) STORED NOT NULL,
    -- Orçado x efetivamente executado (usado para gerar o histórico de manutenção)
    execution_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_bi_type CHECK (item_type IN ('service', 'product', 'labor', 'other')),
    CONSTRAINT ck_bi_reference CHECK (
        (item_type = 'service' AND id_workshop_service IS NOT NULL AND id_product IS NULL)
        OR (item_type = 'product' AND id_product IS NOT NULL AND id_workshop_service IS NULL)
        OR (item_type IN ('labor', 'other') AND id_workshop_service IS NULL AND id_product IS NULL)
    ),
    CONSTRAINT ck_bi_quantity CHECK (quantity > 0),
    CONSTRAINT ck_bi_unit_price CHECK (unit_price >= 0),
    -- O subtotal é coluna gerada (não pode ser gravado); o CHECK explicita a regra.
    CONSTRAINT ck_bi_subtotal CHECK (subtotal = ROUND(quantity * unit_price, 2)),
    CONSTRAINT ck_bi_execution CHECK (
        execution_status IN ('pending', 'executed', 'not_executed')
        AND ((execution_status = 'executed') = (executed_at IS NOT NULL))
    ),
    CONSTRAINT fk_bi_budget
        FOREIGN KEY (id_budget, id_workshop)
        REFERENCES BUDGET (id_budget, id_workshop) ON DELETE RESTRICT,
    CONSTRAINT fk_bi_workshop_service
        FOREIGN KEY (id_workshop_service, id_workshop)
        REFERENCES WORKSHOP_SERVICE (id_workshop_service, id_workshop) ON DELETE RESTRICT,
    CONSTRAINT fk_bi_product
        FOREIGN KEY (id_product, id_workshop)
        REFERENCES PRODUCT (id_product, id_workshop) ON DELETE RESTRICT,
    CONSTRAINT ck_bi_service_item CHECK (id_service_item IS NULL OR item_type = 'product'),
    CONSTRAINT uq_bi_id_budget UNIQUE (id_budget_item, id_budget),
    -- Alvos das FKs que exigem item do mesmo orçamento E de um tipo específico
    CONSTRAINT uq_bi_id_budget_type UNIQUE (id_budget_item, id_budget, item_type),
    -- Alvo das FKs do histórico: item do mesmo orçamento, do tipo certo e EXECUTADO
    CONSTRAINT uq_bi_id_budget_type_exec UNIQUE (id_budget_item, id_budget, item_type, execution_status),
    -- Peça só pode apontar para um item de serviço do MESMO orçamento
    -- (NO ACTION de propósito: permite remover serviço e peças na mesma instrução)
    CONSTRAINT fk_bi_service_item
        FOREIGN KEY (id_service_item, id_budget, service_item_type)
        REFERENCES BUDGET_ITEM (id_budget_item, id_budget, item_type)
);

CREATE INDEX idx_bi_budget ON BUDGET_ITEM (id_budget);
CREATE INDEX idx_bi_workshop_service ON BUDGET_ITEM (id_workshop_service) WHERE id_workshop_service IS NOT NULL;
CREATE INDEX idx_bi_product ON BUDGET_ITEM (id_product) WHERE id_product IS NOT NULL;
CREATE INDEX idx_bi_service_item ON BUDGET_ITEM (id_service_item) WHERE id_service_item IS NOT NULL;

-- =====================================================================
-- 6. REGISTER_MAINTENANCE e REGISTER_MAINTENANCE_PART (histórico do veículo: serviços e peças)
-- =====================================================================

-- Serviços efetivamente realizados. Dois tipos de registro:
--   * item de origem: id_attendance, id_budget e id_budget_item preenchidos JUNTOS;
--     o item precisa ser de SERVIÇO e estar EXECUTADO (fk_rm_budget_item), e o
--     atendimento precisa estar entregue com orçamento aprovado (trigger 9.4);
--   * manual: os três campos de origem NULL (manutenção informada pelo cliente).
-- service_name é o retrato textual: o histórico sobrevive à exclusão/desativação
-- do serviço no catálogo.
CREATE TABLE REGISTER_MAINTENANCE (
    id_register_maintenance BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_vehicle BIGINT NOT NULL REFERENCES VEHICLE (id_vehicle) ON DELETE RESTRICT,
    id_attendance BIGINT,                     -- origem (NULL somente em registros manuais)
    id_budget BIGINT,
    id_budget_item BIGINT UNIQUE,             -- impede registro duplicado do mesmo item
    id_service BIGINT REFERENCES SERVICE (id_service) ON DELETE SET NULL,
    service_name VARCHAR(255) NOT NULL,       -- manutenção realizada (retrato textual)
    date_maintenance TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    mileage_km INT CHECK (mileage_km >= 0),
    observations TEXT,
    -- Constantes (só existem quando há item de origem): a FK abaixo só aceita item
    -- do tipo 'service' E com execution_status 'executed'. Sem item (registro
    -- manual) ficam NULL e a FK é ignorada (MATCH SIMPLE).
    item_type VARCHAR(20)
        GENERATED ALWAYS AS (CASE WHEN id_budget_item IS NOT NULL THEN 'service' END) STORED,
    item_execution_status VARCHAR(20)
        GENERATED ALWAYS AS (CASE WHEN id_budget_item IS NOT NULL THEN 'executed' END) STORED,

    -- Histórico nunca é apagado em cascata: cancele/desative a origem em vez de excluí-la
    CONSTRAINT fk_rm_attendance_vehicle
        FOREIGN KEY (id_attendance, id_vehicle)
        REFERENCES ATTENDANCE (id_attendance, id_vehicle) ON DELETE RESTRICT,
    CONSTRAINT fk_rm_budget
        FOREIGN KEY (id_budget, id_attendance)
        REFERENCES BUDGET (id_budget, id_attendance) ON DELETE RESTRICT,
    CONSTRAINT fk_rm_budget_item
        FOREIGN KEY (id_budget_item, id_budget, item_type, item_execution_status)
        REFERENCES BUDGET_ITEM (id_budget_item, id_budget, item_type, execution_status) ON DELETE RESTRICT,
    -- Origem completa (atendimento + orçamento + item) ou nenhuma (registro manual)
    CONSTRAINT ck_rm_origin CHECK (
        (id_attendance IS NULL AND id_budget IS NULL AND id_budget_item IS NULL)
        OR (id_attendance IS NOT NULL AND id_budget IS NOT NULL AND id_budget_item IS NOT NULL)
    )
);

CREATE INDEX idx_rm_vehicle_date ON REGISTER_MAINTENANCE (id_vehicle, date_maintenance DESC);
CREATE INDEX idx_rm_attendance ON REGISTER_MAINTENANCE (id_attendance) WHERE id_attendance IS NOT NULL;
CREATE INDEX idx_rm_budget ON REGISTER_MAINTENANCE (id_budget) WHERE id_budget IS NOT NULL;

-- Peças/produtos efetivamente utilizados (histórico do veículo). Tabela própria:
-- uma peça NÃO é um serviço e não deve ser registrada como tal em
-- REGISTER_MAINTENANCE. Gerada somente na entrega (register_attendance_history).
-- Cada linha é um retrato do que foi utilizado: descrição, marca, categoria,
-- quantidade e preço no momento do registro; alterar/desativar o produto ou o
-- serviço depois não modifica o histórico.
CREATE TABLE REGISTER_MAINTENANCE_PART (
    id_register_maintenance_part BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_vehicle BIGINT NOT NULL REFERENCES VEHICLE (id_vehicle) ON DELETE RESTRICT,
    id_attendance BIGINT NOT NULL,
    id_budget BIGINT NOT NULL,
    id_workshop BIGINT NOT NULL,              -- oficina que utilizou a peça
    id_budget_item BIGINT NOT NULL UNIQUE,    -- item de origem; impede registro duplicado
    id_service_item BIGINT,                   -- serviço (do mesmo orçamento) ao qual a peça pertence
    id_product BIGINT NOT NULL,               -- produto do catálogo (todo item de produto referencia PRODUCT)
    description VARCHAR(255) NOT NULL,        -- retrato (snapshot)
    brand VARCHAR(255),                       -- retrato da marca no momento do registro
    category VARCHAR(255),                    -- retrato da categoria no momento do registro
    quantity DECIMAL(10, 3) NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10, 2) NOT NULL CHECK (unit_price >= 0),
    date_maintenance TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    mileage_km INT CHECK (mileage_km >= 0),
    observations TEXT,
    -- Constantes: a FK abaixo só aceita item do tipo 'product' E já EXECUTADO
    item_type VARCHAR(20) GENERATED ALWAYS AS ('product') STORED,
    item_execution_status VARCHAR(20) GENERATED ALWAYS AS ('executed') STORED,

    CONSTRAINT fk_rmp_attendance_vehicle
        FOREIGN KEY (id_attendance, id_vehicle)
        REFERENCES ATTENDANCE (id_attendance, id_vehicle) ON DELETE RESTRICT,
    CONSTRAINT fk_rmp_budget_attendance
        FOREIGN KEY (id_budget, id_attendance)
        REFERENCES BUDGET (id_budget, id_attendance) ON DELETE RESTRICT,
    CONSTRAINT fk_rmp_budget_workshop
        FOREIGN KEY (id_budget, id_workshop)
        REFERENCES BUDGET (id_budget, id_workshop) ON DELETE RESTRICT,
    CONSTRAINT fk_rmp_budget_item
        FOREIGN KEY (id_budget_item, id_budget, item_type, item_execution_status)
        REFERENCES BUDGET_ITEM (id_budget_item, id_budget, item_type, execution_status) ON DELETE RESTRICT,
    CONSTRAINT fk_rmp_service_item
        FOREIGN KEY (id_service_item, id_budget)
        REFERENCES BUDGET_ITEM (id_budget_item, id_budget) ON DELETE RESTRICT,
    CONSTRAINT fk_rmp_product
        FOREIGN KEY (id_product, id_workshop)
        REFERENCES PRODUCT (id_product, id_workshop) ON DELETE RESTRICT
);

CREATE INDEX idx_rmp_vehicle_date ON REGISTER_MAINTENANCE_PART (id_vehicle, date_maintenance DESC);
CREATE INDEX idx_rmp_attendance ON REGISTER_MAINTENANCE_PART (id_attendance);
CREATE INDEX idx_rmp_budget ON REGISTER_MAINTENANCE_PART (id_budget);
CREATE INDEX idx_rmp_workshop ON REGISTER_MAINTENANCE_PART (id_workshop);
CREATE INDEX idx_rmp_product ON REGISTER_MAINTENANCE_PART (id_product) WHERE id_product IS NOT NULL;

-- Histórico completo do veículo: serviços (REGISTER_MAINTENANCE) e peças
-- (REGISTER_MAINTENANCE_PART) em uma única consulta, ordenável por data.
CREATE VIEW vw_vehicle_maintenance_history AS
SELECT rm.id_vehicle,
       'service'::TEXT              AS record_type,
       rm.id_register_maintenance   AS id_record,
       rm.id_attendance,
       rm.id_budget,
       rm.id_budget_item,
       a.id_workshop,
       rm.id_service,
       NULL::BIGINT                 AS id_product,
       NULL::BIGINT                 AS id_service_item,
       rm.service_name              AS description,
       NULL::VARCHAR                AS brand,
       NULL::VARCHAR                AS category,
       bi.quantity,
       bi.unit_price,
       rm.date_maintenance,
       rm.mileage_km,
       rm.observations
FROM REGISTER_MAINTENANCE rm
LEFT JOIN ATTENDANCE a   ON a.id_attendance = rm.id_attendance
LEFT JOIN BUDGET_ITEM bi ON bi.id_budget_item = rm.id_budget_item
UNION ALL
SELECT rmp.id_vehicle,
       'part'::TEXT,
       rmp.id_register_maintenance_part,
       rmp.id_attendance,
       rmp.id_budget,
       rmp.id_budget_item,
       rmp.id_workshop,
       NULL::BIGINT,
       rmp.id_product,
       rmp.id_service_item,
       rmp.description,
       rmp.brand,
       rmp.category,
       rmp.quantity,
       rmp.unit_price,
       rmp.date_maintenance,
       rmp.mileage_km,
       rmp.observations
FROM REGISTER_MAINTENANCE_PART rmp;

-- =====================================================================
-- 7. CHAT, MESSAGE, REVIEW, FAVORITE, NOTIFICATION
-- =====================================================================

CREATE TABLE CHAT (
    id_chat BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_client BIGINT NOT NULL REFERENCES CLIENT (id_client) ON DELETE CASCADE,
    id_workshop BIGINT NOT NULL REFERENCES WORKSHOP (id_workshop) ON DELETE CASCADE,
    date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status_chat VARCHAR(50) NOT NULL DEFAULT 'active',

    CONSTRAINT ck_chat_status CHECK (status_chat IN ('active', 'archived', 'closed')),
    -- Necessárias para as FKs compostas de MESSAGE (remetente pertence ao chat)
    CONSTRAINT uq_chat_id_client UNIQUE (id_chat, id_client),
    CONSTRAINT uq_chat_id_workshop UNIQUE (id_chat, id_workshop)
);

CREATE INDEX idx_chat_client ON CHAT (id_client);
CREATE INDEX idx_chat_workshop ON CHAT (id_workshop);

CREATE TABLE MESSAGE (
    id_message BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_chat BIGINT NOT NULL REFERENCES CHAT (id_chat) ON DELETE CASCADE,
    id_client BIGINT,                         -- remetente cliente
    id_workshop BIGINT,                       -- remetente oficina
    content TEXT NOT NULL,
    date_sent TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status_message VARCHAR(50) NOT NULL DEFAULT 'sent',

    CONSTRAINT ck_message_status CHECK (status_message IN ('sent', 'delivered', 'read')),
    -- Exatamente um remetente
    CONSTRAINT ck_message_sender CHECK (NUM_NONNULLS(id_client, id_workshop) = 1),
    -- O remetente precisa ser o participante correspondente do chat
    -- (MATCH SIMPLE: a FK é ignorada quando a coluna do remetente é NULL)
    CONSTRAINT fk_message_chat_client
        FOREIGN KEY (id_chat, id_client)
        REFERENCES CHAT (id_chat, id_client) ON DELETE CASCADE,
    CONSTRAINT fk_message_chat_workshop
        FOREIGN KEY (id_chat, id_workshop)
        REFERENCES CHAT (id_chat, id_workshop) ON DELETE CASCADE
);

CREATE INDEX idx_message_chat_date ON MESSAGE (id_chat, date_sent);

CREATE TABLE REVIEW (
    id_review UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_budget BIGINT NOT NULL UNIQUE REFERENCES BUDGET (id_budget) ON DELETE RESTRICT,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    workshop_response TEXT,
    date_response TIMESTAMPTZ,
    status_review VARCHAR(20) NOT NULL DEFAULT 'published',

    CONSTRAINT ck_review_status CHECK (status_review IN ('published', 'hidden', 'under_review')),
    CONSTRAINT ck_review_response CHECK ((workshop_response IS NULL) = (date_response IS NULL))
);

CREATE TABLE FAVORITE (
    id_favorite BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_client BIGINT NOT NULL REFERENCES CLIENT (id_client) ON DELETE CASCADE,
    id_workshop BIGINT NOT NULL REFERENCES WORKSHOP (id_workshop) ON DELETE CASCADE,
    date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_favorite UNIQUE (id_client, id_workshop)
);

CREATE INDEX idx_favorite_workshop ON FAVORITE (id_workshop);

CREATE TABLE NOTIFICATION (
    id_notification BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_client BIGINT REFERENCES CLIENT (id_client) ON DELETE CASCADE,
    id_workshop BIGINT REFERENCES WORKSHOP (id_workshop) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_status BOOLEAN NOT NULL DEFAULT FALSE,

    -- Exatamente um destinatário
    CONSTRAINT ck_notification_recipient CHECK (NUM_NONNULLS(id_client, id_workshop) = 1)
);

CREATE INDEX idx_notification_client_unread
    ON NOTIFICATION (id_client, date_creation DESC) WHERE id_client IS NOT NULL;
CREATE INDEX idx_notification_workshop_unread
    ON NOTIFICATION (id_workshop, date_creation DESC) WHERE id_workshop IS NOT NULL;

-- =====================================================================
-- 8. PROMOTION, PROMOTION_ADVERTISEMENT e DENUNCIATION
-- =====================================================================

CREATE TABLE PROMOTION (
    id_promotion BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_workshop BIGINT NOT NULL REFERENCES WORKSHOP (id_workshop) ON DELETE RESTRICT,
    id_workshop_service BIGINT,
    id_product BIGINT,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    type_discount VARCHAR(50) NOT NULL,
    discount_value DECIMAL(10, 2) NOT NULL,
    date_start TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_end TIMESTAMPTZ NOT NULL,
    image_url VARCHAR(500),
    status_promotion VARCHAR(50) NOT NULL DEFAULT 'active',

    CONSTRAINT ck_promotion_type CHECK (type_discount IN ('percentage', 'fixed')),
    CONSTRAINT ck_promotion_value CHECK (discount_value > 0),
    CONSTRAINT ck_promotion_status CHECK (status_promotion IN ('active', 'inactive', 'expired')),
    CONSTRAINT ck_promotion_dates CHECK (date_end > date_start),
    CONSTRAINT ck_promotion_discount CHECK (type_discount <> 'percentage' OR discount_value <= 100),
    -- Uma promoção aponta para um serviço OU um produto (ou nenhum, se for geral)
    CONSTRAINT ck_promotion_target CHECK (id_workshop_service IS NULL OR id_product IS NULL),
    -- O serviço/produto precisa pertencer à mesma oficina da promoção.
    -- (NO ACTION em vez de SET NULL: apagar o alvo tornaria a promoção "geral" sem
    --  que a oficina quisesse; desative o serviço/produto em vez de excluí-lo.
    --  Também dispensa ON DELETE SET NULL (coluna), que exige PostgreSQL 15+.)
    CONSTRAINT fk_promotion_workshop_service
        FOREIGN KEY (id_workshop_service, id_workshop)
        REFERENCES WORKSHOP_SERVICE (id_workshop_service, id_workshop),
    CONSTRAINT fk_promotion_product
        FOREIGN KEY (id_product, id_workshop)
        REFERENCES PRODUCT (id_product, id_workshop)
);

CREATE INDEX idx_promotion_workshop_status ON PROMOTION (id_workshop, status_promotion, date_end);
CREATE INDEX idx_promotion_workshop_service ON PROMOTION (id_workshop_service) WHERE id_workshop_service IS NOT NULL;
CREATE INDEX idx_promotion_product ON PROMOTION (id_product) WHERE id_product IS NOT NULL;
-- Apoia expire_promotions(): varre só promoções ativas, por término
CREATE INDEX idx_promotion_active_end ON PROMOTION (date_end) WHERE status_promotion = 'active';

-- status_promotion é o estado PERSISTIDO (administrativo):
--   active   = habilitada pela oficina (pode estar agendada, vigente ou ter
--              passado do fim sem a rotina de expiração ter rodado ainda);
--   inactive = desabilitada pela oficina/administração;
--   expired  = período encerrado (definido por expire_promotions(); estado FINAL).
-- A VIGÊNCIA temporal é derivada das datas. Para listar o que está de fato no ar,
-- use vw_promotion_effective (is_valid_now) e NUNCA apenas status_promotion = 'active'.

-- Contratação de divulgação da promoção no site do SAM (preço cobrado pelo SAM,
-- distinto do desconto concedido pela oficina).
CREATE TABLE PROMOTION_ADVERTISEMENT (
    id_promotion_advertisement BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_promotion BIGINT NOT NULL REFERENCES PROMOTION (id_promotion) ON DELETE RESTRICT,
    image_url VARCHAR(500) NOT NULL,
    date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_start TIMESTAMPTZ NOT NULL,
    date_end TIMESTAMPTZ NOT NULL,
    advertising_price DECIMAL(10, 2) NOT NULL CHECK (advertising_price > 0),
    payment_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    status_advertisement VARCHAR(30) NOT NULL DEFAULT 'pending',

    CONSTRAINT ck_advertisement_payment CHECK (payment_status IN ('pending', 'paid', 'failed', 'refunded')),
    CONSTRAINT ck_advertisement_status CHECK (status_advertisement IN ('pending', 'active', 'completed', 'cancelled')),
    CONSTRAINT ck_advertisement_dates CHECK (date_end > date_start),
    -- Divulgação não pode ficar ativa sem pagamento confirmado
    CONSTRAINT ck_advertisement_paid CHECK (status_advertisement <> 'active' OR payment_status = 'paid')
);

CREATE INDEX idx_advertisement_promotion ON PROMOTION_ADVERTISEMENT (id_promotion);
CREATE INDEX idx_advertisement_active
    ON PROMOTION_ADVERTISEMENT (date_start, date_end) WHERE status_advertisement = 'active';

-- Estado "efetivo" para exibição: nunca mostra como ativa uma promoção/divulgação
-- cujo prazo terminou, mesmo que a rotina de expiração ainda não tenha rodado.
CREATE VIEW vw_promotion_effective AS
SELECT p.*,
       CASE
           WHEN p.status_promotion = 'expired'                      THEN 'expired'
           WHEN p.status_promotion = 'inactive'                     THEN 'inactive'
           WHEN NOW() >= p.date_end                                 THEN 'expired'
           WHEN NOW() <  p.date_start                               THEN 'scheduled'
           ELSE 'active'
       END AS effective_status,
       (p.status_promotion = 'active' AND NOW() >= p.date_start AND NOW() < p.date_end) AS is_valid_now
FROM PROMOTION p;

CREATE VIEW vw_advertisement_effective AS
SELECT ad.*,
       (ad.status_advertisement = 'active'
        AND NOW() >= ad.date_start AND NOW() < ad.date_end
        AND pe.is_valid_now) AS is_running_now
FROM PROMOTION_ADVERTISEMENT ad
JOIN vw_promotion_effective pe ON pe.id_promotion = ad.id_promotion;

-- Denúncias de conteúdo (avaliações, promoções e divulgações). Cada denúncia
-- aponta, por FK tipada, para EXATAMENTE UM conteúdo. RESTRICT em todas as
-- referências: nem a exclusão do conteúdo nem a do cliente apagam o histórico de
-- moderação (desative/oculte o conteúdo por status). Para acrescentar outro tipo
-- de conteúdo (ex.: PRODUCT, MESSAGE), adicione a coluna FK e inclua-a em
-- ck_denunciation_target e nos índices.
CREATE TABLE DENUNCIATION (
    id_denunciation BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_client BIGINT NOT NULL REFERENCES CLIENT (id_client) ON DELETE RESTRICT,
    -- Conteúdo denunciado (exatamente um)
    id_review UUID REFERENCES REVIEW (id_review) ON DELETE RESTRICT,
    id_promotion BIGINT REFERENCES PROMOTION (id_promotion) ON DELETE RESTRICT,
    id_promotion_advertisement BIGINT
        REFERENCES PROMOTION_ADVERTISEMENT (id_promotion_advertisement) ON DELETE RESTRICT,
    reason VARCHAR(50) NOT NULL,
    description TEXT,                         -- explicação adicional (obrigatória se reason = 'other')
    date_creation TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status_denunciation VARCHAR(30) NOT NULL DEFAULT 'pending',
    moderation_decision TEXT,                 -- decisão/justificativa da moderação
    date_resolution TIMESTAMPTZ,              -- preenchida ao resolver (upheld/dismissed)

    CONSTRAINT ck_denunciation_target CHECK (
        NUM_NONNULLS(id_review, id_promotion, id_promotion_advertisement) = 1
    ),
    CONSTRAINT ck_denunciation_reason CHECK (reason IN (
        'inappropriate_content', 'offensive_language', 'harassment',
        'spam', 'false_information', 'fraud', 'other'
    )),
    CONSTRAINT ck_denunciation_reason_other CHECK (
        reason <> 'other' OR NULLIF(BTRIM(description), '') IS NOT NULL
    ),
    -- pending -> in_review -> upheld | dismissed (transições em fn_denunciation_guard)
    CONSTRAINT ck_denunciation_status CHECK (
        status_denunciation IN ('pending', 'in_review', 'upheld', 'dismissed')
    ),
    CONSTRAINT ck_denunciation_resolution CHECK (
        (status_denunciation IN ('pending', 'in_review') AND date_resolution IS NULL)
        OR (status_denunciation IN ('upheld', 'dismissed')
            AND date_resolution IS NOT NULL
            AND NULLIF(BTRIM(moderation_decision), '') IS NOT NULL)
    ),
    CONSTRAINT ck_denunciation_pending_clean CHECK (
        status_denunciation <> 'pending' OR moderation_decision IS NULL
    ),
    CONSTRAINT ck_denunciation_dates CHECK (
        date_resolution IS NULL OR date_resolution >= date_creation
    )
);

-- Fila de moderação e consultas por cliente / por conteúdo
CREATE INDEX idx_denunciation_open
    ON DENUNCIATION (status_denunciation, date_creation)
    WHERE status_denunciation IN ('pending', 'in_review');
CREATE INDEX idx_denunciation_client ON DENUNCIATION (id_client, date_creation DESC);
CREATE INDEX idx_denunciation_review ON DENUNCIATION (id_review) WHERE id_review IS NOT NULL;
CREATE INDEX idx_denunciation_promotion ON DENUNCIATION (id_promotion) WHERE id_promotion IS NOT NULL;
CREATE INDEX idx_denunciation_advertisement
    ON DENUNCIATION (id_promotion_advertisement) WHERE id_promotion_advertisement IS NOT NULL;

-- Um cliente não mantém duas denúncias EM ABERTO sobre o mesmo conteúdo
-- (inclusive sob concorrência). Após a resolução ele pode denunciar de novo.
CREATE UNIQUE INDEX uq_denunciation_open_review
    ON DENUNCIATION (id_client, id_review)
    WHERE id_review IS NOT NULL AND status_denunciation IN ('pending', 'in_review');
CREATE UNIQUE INDEX uq_denunciation_open_promotion
    ON DENUNCIATION (id_client, id_promotion)
    WHERE id_promotion IS NOT NULL AND status_denunciation IN ('pending', 'in_review');
CREATE UNIQUE INDEX uq_denunciation_open_advertisement
    ON DENUNCIATION (id_client, id_promotion_advertisement)
    WHERE id_promotion_advertisement IS NOT NULL AND status_denunciation IN ('pending', 'in_review');

-- =====================================================================
-- 9. FUNÇÕES E TRIGGERS
-- =====================================================================

-- ---------------------------------------------------------------------
-- 9.1 OPERATION_HOUR: impede intervalos sobrepostos na mesma oficina/dia
--     (intervalos consecutivos como 08-12 e 12-18 são permitidos)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_operation_hour_no_overlap()
RETURNS TRIGGER AS $$
BEGIN
    -- Serializa gravações concorrentes da mesma oficina
    PERFORM 1 FROM WORKSHOP WHERE id_workshop = NEW.id_workshop FOR NO KEY UPDATE;

    IF EXISTS (
        SELECT 1
        FROM OPERATION_HOUR oh
        WHERE oh.id_workshop = NEW.id_workshop
          AND oh.day_of_week = NEW.day_of_week
          AND oh.id_operation_hour <> NEW.id_operation_hour
          AND NEW.opening_time < oh.closing_time
          AND NEW.closing_time > oh.opening_time
    ) THEN
        RAISE EXCEPTION 'O intervalo %-% se sobrepõe a outro intervalo da oficina no mesmo dia.',
            NEW.opening_time, NEW.closing_time
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_operation_hour_no_overlap
BEFORE INSERT OR UPDATE OF id_workshop, day_of_week, opening_time, closing_time
ON OPERATION_HOUR
FOR EACH ROW EXECUTE FUNCTION fn_operation_hour_no_overlap();

-- ---------------------------------------------------------------------
-- 9.2 WORKSHOP_SERVICE: solicitação automática + aprovação/rejeição
-- ---------------------------------------------------------------------

-- Serviço personalizado (sem id_service) nasce com solicitação 'pending'.
CREATE OR REPLACE FUNCTION fn_workshop_service_default_request()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.id_service IS NULL AND NEW.status_solicitation IS NULL THEN
        NEW.status_solicitation := 'pending';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_workshop_service_default_request
BEFORE INSERT ON WORKSHOP_SERVICE
FOR EACH ROW EXECUTE FUNCTION fn_workshop_service_default_request();

-- Aprova a solicitação: reaproveita o serviço global de mesmo nome NORMALIZADO
-- (ver normalize_service_name) ou cria um novo, e associa o serviço da oficina a
-- ele. Retorna id_service.
--   * Serviço existente reutilizado: categoria e descrição dele são PRESERVADAS;
--     p_id_category e p_description só valem quando um serviço novo é criado.
--   * Concorrência: a criação usa INSERT ... ON CONFLICT sobre o índice único
--     uq_service_name_normalized. Se outra transação criar/confirmar o mesmo nome
--     ao mesmo tempo, a segunda espera a primeira e passa a reutilizar o registro
--     (nunca duplica, nunca falha por unicidade).
--   * Atomicidade: qualquer erro (inclusive de FK/unicidade) desfaz a chamada
--     inteira; a solicitação continua 'pending'. A linha da solicitação é
--     bloqueada primeiro (FOR UPDATE), então duas aprovações da MESMA solicitação
--     se serializam e a segunda é recusada por já não estar pendente.
--   * Bloqueios: WORKSHOP_SERVICE -> índice de SERVICE. Nenhuma transação
--     concorrente segura o índice esperando a linha de outra, logo não há deadlock.
CREATE OR REPLACE FUNCTION approve_workshop_service_request(
    p_id_workshop_service BIGINT,
    p_id_category BIGINT DEFAULT NULL,
    p_name VARCHAR DEFAULT NULL,
    p_description TEXT DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_ws WORKSHOP_SERVICE%ROWTYPE;
    v_name VARCHAR(255);
    v_normalized TEXT;
    v_id_category BIGINT;
    v_id_service BIGINT;
BEGIN
    SELECT * INTO v_ws
    FROM WORKSHOP_SERVICE
    WHERE id_workshop_service = p_id_workshop_service
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Serviço da oficina % não encontrado.', p_id_workshop_service;
    END IF;
    IF v_ws.status_solicitation IS DISTINCT FROM 'pending' THEN
        RAISE EXCEPTION 'Somente solicitações pendentes podem ser aprovadas (status atual: %).',
            COALESCE(v_ws.status_solicitation, 'serviço do catálogo');
    END IF;

    v_name := COALESCE(NULLIF(clean_service_name(p_name), ''), clean_service_name(v_ws.name_local));
    IF v_name IS NULL OR v_name = '' THEN
        RAISE EXCEPTION 'Informe o nome do serviço global.';
    END IF;
    v_normalized := normalize_service_name(v_name);
    v_id_category := COALESCE(p_id_category, v_ws.id_suggested_category);

    LOOP
        SELECT id_service INTO v_id_service
        FROM SERVICE
        WHERE normalize_service_name(name) = v_normalized;
        EXIT WHEN FOUND;                       -- já existe: reutiliza sem alterá-lo

        IF v_id_category IS NULL THEN
            RAISE EXCEPTION 'Informe a categoria do novo serviço global.';
        END IF;

        INSERT INTO SERVICE (name, description, id_category)
        VALUES (v_name, COALESCE(p_description, v_ws.description_local), v_id_category)
        ON CONFLICT (normalize_service_name(name)) DO NOTHING
        RETURNING id_service INTO v_id_service;
        EXIT WHEN FOUND;                       -- criou

        -- Conflito: outra transação criou o mesmo nome; volta e reutiliza o registro dela.
    END LOOP;

    IF EXISTS (SELECT 1 FROM WORKSHOP_SERVICE
               WHERE id_workshop = v_ws.id_workshop
                 AND id_service = v_id_service
                 AND id_workshop_service <> v_ws.id_workshop_service) THEN
        RAISE EXCEPTION 'A oficina já possui o serviço global "%" em seu catálogo; rejeite esta solicitação.',
            v_name USING ERRCODE = 'unique_violation';
    END IF;

    UPDATE WORKSHOP_SERVICE
    SET id_service = v_id_service,
        status_solicitation = 'approved',
        motivation_rejection = NULL,
        date_solicitation_response = NOW()
    WHERE id_workshop_service = p_id_workshop_service;

    RETURN v_id_service;
END;
$$ LANGUAGE plpgsql;

-- Rejeita a solicitação: o serviço permanece apenas no catálogo da oficina.
CREATE OR REPLACE FUNCTION reject_workshop_service_request(
    p_id_workshop_service BIGINT,
    p_motivation TEXT
) RETURNS VOID AS $$
DECLARE
    v_status VARCHAR(50);
BEGIN
    IF p_motivation IS NULL OR BTRIM(p_motivation) = '' THEN
        RAISE EXCEPTION 'Informe o motivo da rejeição.';
    END IF;

    SELECT status_solicitation INTO v_status
    FROM WORKSHOP_SERVICE
    WHERE id_workshop_service = p_id_workshop_service
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Serviço da oficina % não encontrado.', p_id_workshop_service;
    END IF;
    IF v_status IS DISTINCT FROM 'pending' THEN
        RAISE EXCEPTION 'Somente solicitações pendentes podem ser rejeitadas (status atual: %).',
            COALESCE(v_status, 'serviço do catálogo');
    END IF;

    UPDATE WORKSHOP_SERVICE
    SET status_solicitation = 'rejected',
        motivation_rejection = p_motivation,
        date_solicitation_response = NOW()
    WHERE id_workshop_service = p_id_workshop_service;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 9.3 ATTENDANCE: máquina de estados, vínculo com o orçamento, manutenção
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION attendance_transition_allowed(
    p_old STATUS_ATTENDANCE,
    p_new STATUS_ATTENDANCE
) RETURNS BOOLEAN AS $$
    SELECT CASE p_old
        WHEN 'requested'        THEN p_new IN ('budgeted', 'canceled')
        WHEN 'budgeted'         THEN p_new IN ('waiting_approval', 'requested', 'canceled')
        WHEN 'waiting_approval' THEN p_new IN ('approved', 'requested', 'canceled')
        WHEN 'approved'         THEN p_new IN ('in_progress', 'canceled')
        WHEN 'in_progress'      THEN p_new IN ('completed', 'canceled')
        WHEN 'completed'        THEN p_new IN ('delivered', 'in_progress')
        ELSE FALSE   -- delivered e canceled são estados finais
    END;
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION fn_attendance_before_write()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status_attendance <> 'requested' THEN
            RAISE EXCEPTION 'Um atendimento deve ser criado com status requested (recebido: %).',
                NEW.status_attendance USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.status_attendance = OLD.status_attendance THEN
        RETURN NEW;
    END IF;

    IF NOT attendance_transition_allowed(OLD.status_attendance, NEW.status_attendance) THEN
        RAISE EXCEPTION 'Transição de atendimento inválida: % -> %.',
            OLD.status_attendance, NEW.status_attendance
            USING ERRCODE = 'check_violation';
    END IF;

    -- Estados comerciais pré-aprovação exigem uma proposta em aberto
    IF NEW.status_attendance IN ('budgeted', 'waiting_approval')
       AND NOT EXISTS (SELECT 1 FROM BUDGET
                       WHERE id_attendance = NEW.id_attendance AND status_budget = 'pending') THEN
        RAISE EXCEPTION 'O atendimento % não possui orçamento pendente.', NEW.id_attendance
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status_attendance = 'waiting_approval'
       AND NOT EXISTS (SELECT 1 FROM BUDGET b JOIN BUDGET_ITEM bi USING (id_budget)
                       WHERE b.id_attendance = NEW.id_attendance AND b.status_budget = 'pending') THEN
        RAISE EXCEPTION 'O orçamento pendente do atendimento % não possui itens.', NEW.id_attendance
            USING ERRCODE = 'check_violation';
    END IF;

    -- Aprovação e execução exigem orçamento aprovado (fonte de verdade: BUDGET)
    IF NEW.status_attendance IN ('approved', 'in_progress', 'completed', 'delivered')
       AND NOT EXISTS (SELECT 1 FROM BUDGET
                       WHERE id_attendance = NEW.id_attendance AND status_budget = 'approved') THEN
        RAISE EXCEPTION 'O atendimento % não possui orçamento aprovado.', NEW.id_attendance
            USING ERRCODE = 'check_violation';
    END IF;

    -- Conclusão/entrega: bloqueia o orçamento aprovado ANTES de ler os itens
    -- (ordem ATTENDANCE -> BUDGET). fn_budget_item_guard bloqueia o mesmo orçamento
    -- antes de mudar a execução de um item; assim, uma decisão de execução
    -- concorrente ou é confirmada antes (e é vista abaixo) ou espera e é recusada
    -- porque o atendimento já saiu de in_progress.
    IF NEW.status_attendance IN ('completed', 'delivered') THEN
        PERFORM 1 FROM BUDGET
        WHERE id_attendance = NEW.id_attendance AND status_budget = 'approved'
        FOR NO KEY UPDATE;
    END IF;

    -- Só conclui quando cada serviço E cada produto/peça orçado (itens que geram
    -- histórico) foi marcado como executado/utilizado ou não executado
    IF NEW.status_attendance = 'completed'
       AND EXISTS (SELECT 1 FROM BUDGET b JOIN BUDGET_ITEM bi USING (id_budget)
                   WHERE b.id_attendance = NEW.id_attendance
                     AND b.status_budget = 'approved'
                     AND bi.item_type IN ('service', 'product')
                     AND bi.execution_status = 'pending') THEN
        RAISE EXCEPTION 'Existem serviços ou produtos do orçamento ainda sem situação de execução.'
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_attendance_before_write
BEFORE INSERT OR UPDATE OF status_attendance
ON ATTENDANCE
FOR EACH ROW EXECUTE FUNCTION fn_attendance_before_write();

-- Gera o histórico DEFINITIVO do veículo a partir de um atendimento ENTREGUE:
--   * REGISTER_MAINTENANCE       : um registro por item de SERVIÇO executado;
--   * REGISTER_MAINTENANCE_PART  : um registro por item de PRODUTO/PEÇA utilizado.
-- Itens pendentes ou não executados nunca entram. Considera somente o orçamento
-- aprovado. Idempotente: ON CONFLICT (id_budget_item) DO NOTHING torna seguro
-- chamar de novo (reprocessamento). Retorna quantos registros NOVOS criou.
CREATE OR REPLACE FUNCTION register_attendance_history(p_id_attendance BIGINT)
RETURNS INTEGER AS $$
DECLARE
    v_att ATTENDANCE%ROWTYPE;
    v_services INTEGER;
    v_parts INTEGER;
BEGIN
    SELECT * INTO v_att FROM ATTENDANCE WHERE id_attendance = p_id_attendance;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'O atendimento % não existe.', p_id_attendance;
    END IF;
    IF v_att.status_attendance <> 'delivered' THEN
        RAISE EXCEPTION 'O histórico só é gerado para atendimento entregue (status atual: %).',
            v_att.status_attendance USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO REGISTER_MAINTENANCE (
        id_vehicle, id_attendance, id_budget, id_budget_item,
        id_service, service_name, date_maintenance, mileage_km
    )
    SELECT v_att.id_vehicle, v_att.id_attendance, b.id_budget, bi.id_budget_item,
           ws.id_service, bi.description, COALESCE(bi.executed_at, NOW()), v_att.mileage_km
    FROM BUDGET b
    JOIN BUDGET_ITEM bi ON bi.id_budget = b.id_budget
    LEFT JOIN WORKSHOP_SERVICE ws ON ws.id_workshop_service = bi.id_workshop_service
    WHERE b.id_attendance = v_att.id_attendance
      AND b.status_budget = 'approved'
      AND bi.item_type = 'service'
      AND bi.execution_status = 'executed'
    ON CONFLICT (id_budget_item) DO NOTHING;
    GET DIAGNOSTICS v_services = ROW_COUNT;

    INSERT INTO REGISTER_MAINTENANCE_PART (
        id_vehicle, id_attendance, id_budget, id_workshop, id_budget_item,
        id_service_item, id_product, description, brand, category,
        quantity, unit_price, date_maintenance, mileage_km
    )
    SELECT v_att.id_vehicle, v_att.id_attendance, b.id_budget, b.id_workshop, bi.id_budget_item,
           bi.id_service_item, bi.id_product, bi.description, p.brand, p.category,
           bi.quantity, bi.unit_price, COALESCE(bi.executed_at, NOW()), v_att.mileage_km
    FROM BUDGET b
    JOIN BUDGET_ITEM bi ON bi.id_budget = b.id_budget
    LEFT JOIN PRODUCT p ON p.id_product = bi.id_product
    WHERE b.id_attendance = v_att.id_attendance
      AND b.status_budget = 'approved'
      AND bi.item_type = 'product'
      AND bi.execution_status = 'executed'
    ON CONFLICT (id_budget_item) DO NOTHING;
    GET DIAGNOSTICS v_parts = ROW_COUNT;

    RETURN v_services + v_parts;
END;
$$ LANGUAGE plpgsql;

-- Efeitos da mudança de status:
--   * canceled  -> cancela os orçamentos em aberto/aprovados do atendimento; NÃO
--                  gera histórico (itens já marcados como executados permanecem
--                  apenas no orçamento cancelado);
--   * delivered -> ÚNICA condição que gera histórico (serviços e peças
--                  efetivamente executados/utilizados): register_attendance_history.
--                  Orçamento recusado/expirado/cancelado nunca gera histórico.
CREATE OR REPLACE FUNCTION fn_attendance_after_status()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status_attendance = 'canceled' THEN
        UPDATE BUDGET
        SET status_budget = 'cancelled'
        WHERE id_attendance = NEW.id_attendance
          AND status_budget IN ('pending', 'approved');

    ELSIF NEW.status_attendance = 'delivered' THEN
        PERFORM register_attendance_history(NEW.id_attendance);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_attendance_after_status
AFTER UPDATE OF status_attendance
ON ATTENDANCE
FOR EACH ROW
WHEN (OLD.status_attendance IS DISTINCT FROM NEW.status_attendance)
EXECUTE FUNCTION fn_attendance_after_status();

-- ---------------------------------------------------------------------
-- 9.4 REGISTER_MAINTENANCE / REGISTER_MAINTENANCE_PART: validação da origem
--     Registro com item de origem só é aceito com o atendimento 'delivered' e o
--     orçamento 'approved' (recusa, expiração e cancelamento nunca geram
--     histórico). As demais regras são garantidas por FKs:
--       * item do tipo correto e já EXECUTADO: fk_rm_budget_item / fk_rmp_budget_item;
--       * veículo, atendimento, orçamento e oficina corretos: FKs compostas.
--     Registros manuais (sem item de origem) não passam por estas validações.
--     'delivered' é estado final e o orçamento aprovado de um atendimento entregue
--     não muda mais; por isso a leitura sem bloqueio é segura.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_register_maintenance_origin_guard()
RETURNS TRIGGER AS $$
DECLARE
    v_att_status STATUS_ATTENDANCE;
    v_budget_status VARCHAR(50);
BEGIN
    IF NEW.id_budget_item IS NULL THEN
        RETURN NEW;                            -- registro manual
    END IF;

    SELECT a.status_attendance, b.status_budget
    INTO v_att_status, v_budget_status
    FROM BUDGET b
    JOIN ATTENDANCE a ON a.id_attendance = b.id_attendance
    WHERE b.id_budget = NEW.id_budget;

    IF NOT FOUND THEN
        RETURN NEW;                            -- as FKs recusam a origem inexistente
    END IF;

    IF v_budget_status IS DISTINCT FROM 'approved' THEN
        RAISE EXCEPTION 'O histórico exige orçamento aprovado (status atual: %).', v_budget_status
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_att_status IS DISTINCT FROM 'delivered' THEN
        RAISE EXCEPTION 'O histórico só pode ser registrado para atendimento entregue (status atual: %).',
            v_att_status USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rm_origin_guard
BEFORE INSERT OR UPDATE OF id_vehicle, id_attendance, id_budget, id_budget_item
ON REGISTER_MAINTENANCE
FOR EACH ROW EXECUTE FUNCTION fn_register_maintenance_origin_guard();

CREATE TRIGGER trg_rmp_origin_guard
BEFORE INSERT OR UPDATE OF id_vehicle, id_attendance, id_budget, id_budget_item
ON REGISTER_MAINTENANCE_PART
FOR EACH ROW EXECUTE FUNCTION fn_register_maintenance_origin_guard();

-- A peça registrada precisa ser o mesmo produto (e o mesmo serviço de origem)
-- do item de orçamento que a originou.
CREATE OR REPLACE FUNCTION fn_register_maintenance_part_item_match()
RETURNS TRIGGER AS $$
DECLARE
    v_product BIGINT;
    v_service_item BIGINT;
BEGIN
    SELECT bi.id_product, bi.id_service_item
    INTO v_product, v_service_item
    FROM BUDGET_ITEM bi
    WHERE bi.id_budget_item = NEW.id_budget_item
      AND bi.id_budget = NEW.id_budget;

    IF NOT FOUND THEN
        RETURN NEW;                            -- as FKs recusam o item inexistente
    END IF;

    IF NEW.id_product IS DISTINCT FROM v_product
       OR NEW.id_service_item IS DISTINCT FROM v_service_item THEN
        RAISE EXCEPTION 'O produto/serviço de origem da peça registrada difere do item de orçamento %.',
            NEW.id_budget_item USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rmp_item_match
BEFORE INSERT OR UPDATE OF id_budget_item, id_budget, id_product, id_service_item
ON REGISTER_MAINTENANCE_PART
FOR EACH ROW EXECUTE FUNCTION fn_register_maintenance_part_item_match();

-- ---------------------------------------------------------------------
-- 9.5 BUDGET: ciclo de vida comercial e sincronização com o atendimento
--     Regras:
--       * criado sempre 'pending' e com total 0 (o total vem dos itens);
--       * atendimento passa a 'budgeted' ao receber o orçamento;
--       * a oficina "envia" a proposta movendo o atendimento para waiting_approval;
--       * aprovar o orçamento exige atendimento em waiting_approval, validade em dia
--         (NOW() < date_validity) e ao menos um item; aprova o atendimento
--         automaticamente;
--       * expirar só é possível quando a validade terminou (NOW() >= date_validity);
--         a rotina expire_pending_budgets() faz isso em lote;
--       * rejeitar/expirar/cancelar devolve o atendimento a 'requested';
--       * orçamento aprovado só é cancelado junto com o atendimento;
--       * date_validity só pode mudar enquanto o orçamento continua 'pending';
--       * transições: pending -> approved|rejected|cancelled|expired; approved -> cancelled;
--       * o atendimento é lido com FOR NO KEY UPDATE: o status do atendimento
--         validado é o mesmo que será sincronizado no trigger AFTER (sem janela
--         para uma mudança concorrente).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_budget_before_write()
RETURNS TRIGGER AS $$
DECLARE
    v_att_workshop BIGINT;
    v_att_status STATUS_ATTENDANCE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT id_workshop, status_attendance
        INTO v_att_workshop, v_att_status
        FROM ATTENDANCE
        WHERE id_attendance = NEW.id_attendance
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'O atendimento % não existe.', NEW.id_attendance
                USING ERRCODE = 'foreign_key_violation';
        END IF;

        IF NEW.id_workshop IS NULL THEN
            NEW.id_workshop := v_att_workshop;
        END IF;
        IF v_att_status NOT IN ('requested', 'budgeted') THEN
            RAISE EXCEPTION 'Não é possível criar orçamento para atendimento com status %.', v_att_status
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.status_budget <> 'pending' THEN
            RAISE EXCEPTION 'Um orçamento deve ser criado com status pending.'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.total_price <> 0 THEN
            RAISE EXCEPTION 'total_price é calculado a partir dos itens do orçamento.'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    -- UPDATE
    IF NEW.id_attendance IS DISTINCT FROM OLD.id_attendance
       OR NEW.id_workshop IS DISTINCT FROM OLD.id_workshop THEN
        RAISE EXCEPTION 'O atendimento/oficina de um orçamento não pode ser alterado.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- total_price só pode ser alterado pelo trigger dos itens (profundidade >= 2)
    IF NEW.total_price IS DISTINCT FROM OLD.total_price AND pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'total_price é calculado automaticamente a partir dos itens.'
            USING ERRCODE = 'check_violation';
    END IF;

    -- A validade só pode ser alterada enquanto o orçamento permanece pendente
    -- (impede "estender" um orçamento expirado/aprovado ou expirar antes da hora
    -- encurtando a validade na mesma instrução)
    IF NEW.date_validity IS DISTINCT FROM OLD.date_validity
       AND (OLD.status_budget <> 'pending' OR NEW.status_budget <> 'pending') THEN
        RAISE EXCEPTION 'A validade só pode ser alterada em orçamento que permanece pendente.'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status_budget IS DISTINCT FROM OLD.status_budget THEN
        IF NOT (OLD.status_budget = 'pending'
                OR (OLD.status_budget = 'approved' AND NEW.status_budget = 'cancelled')) THEN
            RAISE EXCEPTION 'Transição de orçamento inválida: % -> %.',
                OLD.status_budget, NEW.status_budget
                USING ERRCODE = 'check_violation';
        END IF;

        -- Bloqueia o atendimento (ordem de bloqueio da INSERÇÃO: ATTENDANCE -> BUDGET)
        -- e lê o status JÁ confirmado por qualquer transação concorrente.
        SELECT status_attendance INTO v_att_status
        FROM ATTENDANCE WHERE id_attendance = NEW.id_attendance
        FOR NO KEY UPDATE;

        IF NEW.status_budget = 'approved' THEN
            IF v_att_status <> 'waiting_approval' THEN
                RAISE EXCEPTION 'O orçamento só pode ser aprovado com o atendimento em waiting_approval (atual: %).',
                    v_att_status USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.date_validity <= NOW() THEN
                RAISE EXCEPTION 'O orçamento está fora da validade (venceu em %).', NEW.date_validity
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM BUDGET_ITEM WHERE id_budget = NEW.id_budget) THEN
                RAISE EXCEPTION 'Um orçamento sem itens não pode ser aprovado.'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;

        IF NEW.status_budget = 'expired' AND OLD.date_validity > NOW() THEN
            RAISE EXCEPTION 'O orçamento ainda está dentro da validade (até %) e não pode expirar.', OLD.date_validity
                USING ERRCODE = 'check_violation';
        END IF;

        IF OLD.status_budget = 'approved' THEN
            IF v_att_status <> 'canceled' THEN
                RAISE EXCEPTION 'Um orçamento aprovado só é cancelado junto com o atendimento.'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF EXISTS (SELECT 1 FROM REVIEW WHERE id_budget = NEW.id_budget) THEN
                RAISE EXCEPTION 'O orçamento já possui avaliação e não pode ser cancelado.'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;

        IF NEW.status_budget IN ('approved', 'rejected') AND NEW.date_response IS NULL THEN
            NEW.date_response := NOW();
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_budget_before_write
BEFORE INSERT OR UPDATE
ON BUDGET
FOR EACH ROW EXECUTE FUNCTION fn_budget_before_write();

CREATE OR REPLACE FUNCTION fn_budget_after_write()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE ATTENDANCE
        SET status_attendance = 'budgeted'
        WHERE id_attendance = NEW.id_attendance AND status_attendance = 'requested';

    ELSIF NEW.status_budget IS DISTINCT FROM OLD.status_budget THEN
        IF NEW.status_budget = 'approved' THEN
            UPDATE ATTENDANCE
            SET status_attendance = 'approved'
            WHERE id_attendance = NEW.id_attendance AND status_attendance = 'waiting_approval';

        ELSIF NEW.status_budget IN ('rejected', 'expired', 'cancelled') THEN
            UPDATE ATTENDANCE
            SET status_attendance = 'requested'
            WHERE id_attendance = NEW.id_attendance
              AND status_attendance IN ('budgeted', 'waiting_approval');
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_budget_after_write
AFTER INSERT OR UPDATE OF status_budget
ON BUDGET
FOR EACH ROW EXECUTE FUNCTION fn_budget_after_write();

-- Expira em lote os orçamentos PENDENTES cuja validade terminou (NOW() >= date_validity).
-- Retorna quantos orçamentos foram marcados como 'expired'.
--   * Usa o UPDATE normal: fn_budget_before_write revalida a regra e
--     fn_budget_after_write devolve o atendimento a 'requested'.
--   * Só toca em orçamentos 'pending'; aprovados/recusados/cancelados/expirados
--     nunca são alterados. Não mexe em itens, valores nem histórico de manutenção.
--   * Idempotente: a 2ª execução seguida retorna 0.
--   * Sem deadlock: bloqueia ATTENDANCE e depois BUDGET (a mesma ordem das demais
--     rotinas) com SKIP LOCKED; o que estiver em uso por outra transação é pulado
--     e tratado na próxima execução (aprovações/cancelamentos concorrentes nunca
--     ficam esperando esta rotina e vice-versa).
-- O tempo NÃO avança triggers sozinho: agende esta função (ver run_expiration_jobs).
CREATE OR REPLACE FUNCTION expire_pending_budgets()
RETURNS INTEGER AS $$
DECLARE
    r RECORD;
    v_count INTEGER := 0;
BEGIN
    FOR r IN
        SELECT id_budget, id_attendance
        FROM BUDGET
        WHERE status_budget = 'pending' AND date_validity <= NOW()
        ORDER BY id_attendance, id_budget
    LOOP
        PERFORM 1 FROM ATTENDANCE
        WHERE id_attendance = r.id_attendance
        FOR NO KEY UPDATE SKIP LOCKED;
        CONTINUE WHEN NOT FOUND;

        PERFORM 1 FROM BUDGET
        WHERE id_budget = r.id_budget
          AND status_budget = 'pending' AND date_validity <= NOW()
        FOR UPDATE SKIP LOCKED;
        CONTINUE WHEN NOT FOUND;               -- já tratado/em uso por outra transação

        UPDATE BUDGET
        SET status_budget = 'expired'
        WHERE id_budget = r.id_budget
          AND status_budget = 'pending' AND date_validity <= NOW();
        IF FOUND THEN
            v_count := v_count + 1;
        END IF;
    END LOOP;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 9.6 BUDGET_ITEM: proteção do snapshot + total do orçamento
-- ---------------------------------------------------------------------

-- Itens só mudam (preço, quantidade, descrição, inclusão/remoção) enquanto o
-- orçamento está 'pending'. Após a aprovação, apenas a situação de execução
-- pode ser atualizada. O lock FOR UPDATE no orçamento serializa operações
-- concorrentes sobre os itens do mesmo orçamento.
CREATE OR REPLACE FUNCTION fn_budget_item_guard()
RETURNS TRIGGER AS $$
DECLARE
    v_id_budget BIGINT;
    v_status VARCHAR(50);
    v_workshop BIGINT;
    v_id_attendance BIGINT;
    v_att_status STATUS_ATTENDANCE;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_id_budget := OLD.id_budget;
    ELSE
        v_id_budget := NEW.id_budget;
    END IF;

    SELECT status_budget, id_workshop, id_attendance
    INTO v_status, v_workshop, v_id_attendance
    FROM BUDGET
    WHERE id_budget = v_id_budget
    FOR UPDATE;

    IF NOT FOUND THEN
        -- fk_bi_budget é RESTRICT: itens nunca são removidos em cascata
        RAISE EXCEPTION 'O orçamento % não existe.', v_id_budget
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.id_workshop IS NULL THEN
            NEW.id_workshop := v_workshop;
        END IF;
        IF v_status <> 'pending' THEN
            RAISE EXCEPTION 'Itens só podem ser incluídos em orçamento pendente (status: %).', v_status
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.execution_status <> 'pending' THEN
            RAISE EXCEPTION 'Um item novo deve iniciar com execution_status pending.'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.id_budget IS DISTINCT FROM OLD.id_budget
           OR NEW.id_workshop IS DISTINCT FROM OLD.id_workshop THEN
            RAISE EXCEPTION 'Um item não pode ser movido para outro orçamento.'
                USING ERRCODE = 'check_violation';
        END IF;

        IF v_status <> 'pending'
           AND (NEW.item_type, NEW.id_workshop_service, NEW.id_product, NEW.id_service_item,
                NEW.description, NEW.quantity, NEW.unit_price)
               IS DISTINCT FROM
               (OLD.item_type, OLD.id_workshop_service, OLD.id_product, OLD.id_service_item,
                OLD.description, OLD.quantity, OLD.unit_price) THEN
            RAISE EXCEPTION 'Os dados comerciais do item são imutáveis após o envio do orçamento (status: %).', v_status
                USING ERRCODE = 'check_violation';
        END IF;

        IF NEW.execution_status IS DISTINCT FROM OLD.execution_status THEN
            SELECT status_attendance INTO v_att_status
            FROM ATTENDANCE WHERE id_attendance = v_id_attendance;

            -- Decisões de execução só durante a execução (in_progress). Antes disso
            -- (approved) pularia a sequência approved -> in_progress; depois
            -- (completed/delivered) alteraria um atendimento já concluído. Para
            -- corrigir uma decisão, reabra o atendimento (completed -> in_progress).
            IF v_status <> 'approved' OR v_att_status <> 'in_progress' THEN
                RAISE EXCEPTION 'A execução só pode ser registrada em orçamento aprovado com o atendimento em in_progress (atual: %).',
                    v_att_status
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;

        IF NEW.execution_status = 'executed' THEN
            NEW.executed_at := COALESCE(NEW.executed_at, NOW());
        ELSE
            NEW.executed_at := NULL;
        END IF;
        RETURN NEW;

    ELSE  -- DELETE
        IF v_status <> 'pending' THEN
            RAISE EXCEPTION 'Itens só podem ser removidos de orçamento pendente (status: %).', v_status
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_budget_item_guard
BEFORE INSERT OR UPDATE OR DELETE
ON BUDGET_ITEM
FOR EACH ROW EXECUTE FUNCTION fn_budget_item_guard();

-- total_price = soma dos subtotais. O orçamento já está bloqueado (FOR UPDATE)
-- pelo trigger BEFORE; a soma roda em instrução separada (novo snapshot em
-- READ COMMITTED) e enxerga itens confirmados por transações concorrentes.
CREATE OR REPLACE FUNCTION fn_budget_item_recalc_total()
RETURNS TRIGGER AS $$
DECLARE
    v_id_budget BIGINT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_id_budget := OLD.id_budget;
    ELSE
        v_id_budget := NEW.id_budget;
    END IF;

    PERFORM 1 FROM BUDGET WHERE id_budget = v_id_budget FOR UPDATE;

    UPDATE BUDGET b
    SET total_price = s.total
    FROM (
        SELECT COALESCE(SUM(subtotal), 0) AS total
        FROM BUDGET_ITEM
        WHERE id_budget = v_id_budget
    ) s
    WHERE b.id_budget = v_id_budget
      AND b.total_price IS DISTINCT FROM s.total;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_budget_item_recalc_total
AFTER INSERT OR UPDATE OF quantity, unit_price OR DELETE
ON BUDGET_ITEM
FOR EACH ROW EXECUTE FUNCTION fn_budget_item_recalc_total();

-- ---------------------------------------------------------------------
-- 9.7 REVIEW: só após entrega
--     Exige orçamento 'approved' E atendimento 'delivered'. Trava atendimento e
--     orçamento (FOR SHARE, nessa ordem — a mesma dos demais fluxos) para que
--     nenhuma mudança de status concorrente invalide a avaliação durante a
--     validação. Depois de criada, o orçamento aprovado não pode ser cancelado
--     (ver fn_budget_before_write) e 'delivered' é estado final.
--     Obs.: que o orçamento pertence ao cliente autenticado é validado no backend.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION validate_review_budget()
RETURNS TRIGGER AS $$
DECLARE
    v_id_attendance BIGINT;
    v_status_budget VARCHAR(50);
    v_status_attendance STATUS_ATTENDANCE;
BEGIN
    SELECT id_attendance INTO v_id_attendance
    FROM BUDGET WHERE id_budget = NEW.id_budget;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'O orçamento informado não existe.'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT status_attendance INTO v_status_attendance
    FROM ATTENDANCE WHERE id_attendance = v_id_attendance
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'O orçamento informado não está vinculado a um atendimento válido.'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT status_budget INTO v_status_budget
    FROM BUDGET WHERE id_budget = NEW.id_budget
    FOR SHARE;

    IF v_status_budget IS DISTINCT FROM 'approved' THEN
        RAISE EXCEPTION 'A avaliação exige um orçamento aprovado (status atual: %).', v_status_budget
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_status_attendance IS DISTINCT FROM 'delivered' THEN
        RAISE EXCEPTION 'A avaliação só pode ser realizada após a entrega do veículo (atendimento: %).',
            v_status_attendance
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_review_budget
BEFORE INSERT OR UPDATE OF id_budget
ON REVIEW
FOR EACH ROW EXECUTE FUNCTION validate_review_budget();

-- ---------------------------------------------------------------------
-- 9.8 PROMOTION: período, ativação, expiração e efeito nas divulgações
--     Regras:
--       * ck_promotion_dates garante date_end > date_start;
--       * 'active' só pode ser definido (INSERT, reativação ou mudança de datas)
--         enquanto NOW() < date_end; uma promoção AGENDADA (date_start futuro) pode
--         ser 'active' e só passa a valer em date_start (ver vw_promotion_effective);
--       * 'expired' só a partir de 'active', com o período encerrado
--         (NOW() >= date_end), e é estado FINAL: nunca reativa nem muda de datas
--         (para repetir a oferta, crie uma nova promoção);
--       * 'inactive' <-> 'active' é decisão da oficina/administração;
--       * ao virar 'inactive' ou 'expired', as divulgações pendentes/ativas são
--         encerradas (histórico preservado: nada é apagado).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_promotion_validate()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status_promotion = 'expired' THEN
        IF (NEW.status_promotion, NEW.date_start, NEW.date_end)
           IS DISTINCT FROM (OLD.status_promotion, OLD.date_start, OLD.date_end) THEN
            RAISE EXCEPTION 'Uma promoção expirada é definitiva: crie uma nova promoção em vez de reativá-la.'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.status_promotion = 'expired' THEN
        IF TG_OP = 'INSERT' THEN
            RAISE EXCEPTION 'Uma promoção não pode ser criada já expirada.'
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.status_promotion <> 'active' THEN
            RAISE EXCEPTION 'Somente uma promoção ativa pode expirar (status atual: %).', OLD.status_promotion
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.date_end > NOW() THEN
            RAISE EXCEPTION 'A promoção ainda está no período (até %) e não pode expirar.', OLD.date_end
                USING ERRCODE = 'check_violation';
        END IF;

    ELSIF NEW.status_promotion = 'active'
          AND (TG_OP = 'INSERT'
               OR OLD.status_promotion <> 'active'
               OR NEW.date_start IS DISTINCT FROM OLD.date_start
               OR NEW.date_end IS DISTINCT FROM OLD.date_end) THEN
        IF NEW.date_end <= NOW() THEN
            RAISE EXCEPTION 'Uma promoção não pode ser ativada fora do período de validade (terminou em %).', NEW.date_end
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_promotion_validate
BEFORE INSERT OR UPDATE OF status_promotion, date_start, date_end
ON PROMOTION
FOR EACH ROW EXECUTE FUNCTION fn_promotion_validate();

-- Promoção desativada/expirada: a divulgação não pode continuar no ar.
--   * ativa + promoção expirou -> 'completed' (veiculou até o fim da promoção);
--   * demais (pendente, ou ativa com promoção desativada) -> 'cancelled'.
-- payment_status NÃO é alterado: estorno/reembolso é regra do backend.
CREATE OR REPLACE FUNCTION fn_promotion_close_advertisements()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE PROMOTION_ADVERTISEMENT
    SET status_advertisement = CASE
            WHEN NEW.status_promotion = 'expired' AND status_advertisement = 'active'
                THEN 'completed'
            ELSE 'cancelled'
        END
    WHERE id_promotion = NEW.id_promotion
      AND status_advertisement IN ('pending', 'active');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_promotion_close_advertisements
AFTER UPDATE OF status_promotion
ON PROMOTION
FOR EACH ROW
WHEN (NEW.status_promotion IN ('inactive', 'expired')
      AND OLD.status_promotion IS DISTINCT FROM NEW.status_promotion)
EXECUTE FUNCTION fn_promotion_close_advertisements();

-- Expira as promoções ATIVAS cujo período terminou (NOW() >= date_end). O trigger
-- acima encerra as divulgações delas. Retorna quantas promoções expiraram.
-- Nunca reativa nada; promoções 'inactive' não são tocadas. Idempotente.
-- SKIP LOCKED: linhas em uso por outra transação ficam para a próxima execução.
CREATE OR REPLACE FUNCTION expire_promotions()
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    WITH due AS (
        SELECT id_promotion
        FROM PROMOTION
        WHERE status_promotion = 'active' AND date_end <= NOW()
        ORDER BY id_promotion
        FOR UPDATE SKIP LOCKED
    ), upd AS (
        UPDATE PROMOTION p
        SET status_promotion = 'expired'
        FROM due
        WHERE p.id_promotion = due.id_promotion
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_count FROM upd;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- Conclui as divulgações 'active' cujo próprio período (date_end) terminou.
-- Retorna quantas foram concluídas. Idempotente.
CREATE OR REPLACE FUNCTION complete_finished_advertisements()
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    WITH due AS (
        SELECT id_promotion_advertisement
        FROM PROMOTION_ADVERTISEMENT
        WHERE status_advertisement = 'active' AND date_end <= NOW()
        ORDER BY id_promotion_advertisement
        FOR UPDATE SKIP LOCKED
    ), upd AS (
        UPDATE PROMOTION_ADVERTISEMENT ad
        SET status_advertisement = 'completed'
        FROM due
        WHERE ad.id_promotion_advertisement = due.id_promotion_advertisement
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_count FROM upd;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 9.9 PROMOTION_ADVERTISEMENT: promoção precisa estar válida
--     * contratar (INSERT) ou trocar a promoção: promoção 'active' e ainda no
--       prazo (NOW() < date_end);
--     * colocar a divulgação no ar (status 'active'): promoção vigente agora
--       (date_start <= NOW() < date_end).
--     Bloqueio da promoção: FOR SHARE no INSERT (ordem PROMOTION -> divulgação,
--     igual à do trigger de encerramento); FOR KEY SHARE no UPDATE (a linha da
--     divulgação já está bloqueada; evita a ordem inversa e o deadlock com a
--     desativação da promoção, cujo trigger AFTER encerra a divulgação
--     depois que esta transação confirmar).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_promotion_advertisement_validate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_promotion_status VARCHAR(50);
    v_promotion_start TIMESTAMPTZ;
    v_promotion_end TIMESTAMPTZ;
    v_validate BOOLEAN;
BEGIN
    -- Só revalida a promoção quando os campos relevantes mudarem.
    IF TG_OP = 'INSERT' THEN
        v_validate := TRUE;
    ELSE
        v_validate :=
            NEW.id_promotion IS DISTINCT FROM OLD.id_promotion
            OR NEW.date_start IS DISTINCT FROM OLD.date_start
            OR NEW.date_end IS DISTINCT FROM OLD.date_end
            OR (
                NEW.status_advertisement = 'active'
                AND OLD.status_advertisement IS DISTINCT FROM 'active'
            );
    END IF;

    IF NOT v_validate THEN
        RETURN NEW;
    END IF;

    SELECT status_promotion, date_start, date_end
    INTO v_promotion_status, v_promotion_start, v_promotion_end
    FROM PROMOTION
    WHERE id_promotion = NEW.id_promotion
    FOR KEY SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'A promoção informada não existe.';
    END IF;

    IF v_promotion_status <> 'active' THEN
        RAISE EXCEPTION 'A divulgação exige uma promoção ativa.';
    END IF;

    -- O período da divulgação precisa estar dentro do período da promoção.
    IF NEW.date_start < v_promotion_start
       OR NEW.date_end > v_promotion_end THEN
        RAISE EXCEPTION
            'O período da divulgação deve estar contido no período da promoção.';
    END IF;

    -- Uma nova divulgação ou alteração de período não pode terminar no passado.
    IF (TG_OP = 'INSERT'
        OR NEW.id_promotion IS DISTINCT FROM OLD.id_promotion
        OR NEW.date_start IS DISTINCT FROM OLD.date_start
        OR NEW.date_end IS DISTINCT FROM OLD.date_end)
       AND NEW.date_end <= NOW() THEN
        RAISE EXCEPTION 'O período da divulgação já terminou.';
    END IF;

    -- Uma divulgação só pode ficar ativa durante sua vigência e após pagamento.
    IF NEW.status_advertisement = 'active' THEN
        IF NEW.payment_status <> 'paid' THEN
            RAISE EXCEPTION
                'A divulgação só pode ser ativada após a confirmação do pagamento.';
        END IF;

        IF NEW.date_start > NOW() OR NEW.date_end <= NOW() THEN
            RAISE EXCEPTION
                'A divulgação só pode ser ativada dentro do período contratado.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_promotion_advertisement_validate
BEFORE INSERT OR UPDATE OF
    id_promotion,
    status_advertisement,
    date_start,
    date_end
ON PROMOTION_ADVERTISEMENT
FOR EACH ROW
EXECUTE FUNCTION fn_promotion_advertisement_validate();

-- ---------------------------------------------------------------------
-- 9.10 DENUNCIATION: ciclo de moderação e imutabilidade do histórico
--      pending -> in_review -> upheld | dismissed   (pending também pode ser
--      resolvida direto). upheld/dismissed são finais. Cliente, conteúdo e
--      data de criação nunca mudam; motivo/descrição só enquanto 'pending';
--      a decisão registrada na resolução não pode ser reescrita.
--      Ocultar o conteúdo denunciado (ex.: REVIEW 'hidden') é decisão do backend.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION denunciation_transition_allowed(
    p_old VARCHAR,
    p_new VARCHAR
) RETURNS BOOLEAN AS $$
    SELECT CASE p_old
        WHEN 'pending'   THEN p_new IN ('in_review', 'upheld', 'dismissed')
        WHEN 'in_review' THEN p_new IN ('upheld', 'dismissed')
        ELSE FALSE                               -- upheld e dismissed são finais
    END;
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION fn_denunciation_guard()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status_denunciation <> 'pending'
           OR NEW.moderation_decision IS NOT NULL
           OR NEW.date_resolution IS NOT NULL THEN
            RAISE EXCEPTION 'Uma denúncia deve ser criada como pending, sem decisão nem data de resolução.'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    IF (NEW.id_client, NEW.id_review, NEW.id_promotion, NEW.id_promotion_advertisement, NEW.date_creation)
       IS DISTINCT FROM
       (OLD.id_client, OLD.id_review, OLD.id_promotion, OLD.id_promotion_advertisement, OLD.date_creation) THEN
        RAISE EXCEPTION 'Cliente, conteúdo denunciado e data de criação de uma denúncia não podem ser alterados.'
            USING ERRCODE = 'check_violation';
    END IF;

    IF OLD.status_denunciation <> 'pending'
       AND (NEW.reason, NEW.description) IS DISTINCT FROM (OLD.reason, OLD.description) THEN
        RAISE EXCEPTION 'O motivo e a descrição só podem ser alterados enquanto a denúncia está pending.'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status_denunciation IS DISTINCT FROM OLD.status_denunciation THEN
        IF NOT denunciation_transition_allowed(OLD.status_denunciation, NEW.status_denunciation) THEN
            RAISE EXCEPTION 'Transição de denúncia inválida: % -> %.',
                OLD.status_denunciation, NEW.status_denunciation
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.status_denunciation IN ('upheld', 'dismissed') AND NEW.date_resolution IS NULL THEN
            NEW.date_resolution := NOW();
        END IF;
    ELSIF OLD.status_denunciation IN ('upheld', 'dismissed')
          AND (NEW.moderation_decision, NEW.date_resolution)
              IS DISTINCT FROM (OLD.moderation_decision, OLD.date_resolution) THEN
        RAISE EXCEPTION 'A decisão de uma denúncia já resolvida não pode ser alterada.'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_denunciation_guard
BEFORE INSERT OR UPDATE
ON DENUNCIATION
FOR EACH ROW EXECUTE FUNCTION fn_denunciation_guard();

-- ---------------------------------------------------------------------
-- 9.11 Rotinas periódicas de expiração (ponto único de agendamento)
--      O PostgreSQL não dispara triggers com a passagem do tempo: alguém precisa
--      chamar run_expiration_jobs() periodicamente (a cada 1-5 min é suficiente;
--      a vigência na exibição já é correta entre uma execução e outra, pelas
--      views vw_promotion_effective / vw_advertisement_effective).
--
--      Opção A - backend (cron, scheduler da aplicação, Kubernetes CronJob...):
--          psql "$DATABASE_URL" -c "SELECT * FROM run_expiration_jobs();"
--      Opção B - pg_cron (OPCIONAL; exige a extensão instalada pelo DBA e criada
--          no banco onde ela estiver habilitada - este script NÃO a requer):
--          SELECT cron.schedule('sam-expirations', '*/5 * * * *',
--                               $job$SELECT run_expiration_jobs()$job$);
--      É seguro executar a rotina em paralelo e repetidamente (idempotente).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION run_expiration_jobs()
RETURNS TABLE (
    budgets_expired INTEGER,
    promotions_expired INTEGER,
    advertisements_completed INTEGER
) AS $$
BEGIN
    budgets_expired := expire_pending_budgets();
    promotions_expired := expire_promotions();
    advertisements_completed := complete_finished_advertisements();
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

COMMIT;
