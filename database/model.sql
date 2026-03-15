-- 银行流水中间表
DROP TABLE IF EXISTS bank_flow;

CREATE TABLE bank_flow (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date DATE,
    project VARCHAR(100),
    summary VARCHAR(255),
    income DECIMAL(12,2),
    expense DECIMAL(12,2)
);

-- 总台账
DROP TABLE IF EXISTS ledger;

CREATE TABLE ledger (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date DATE,
    project VARCHAR(100),
    summary VARCHAR(255),
    income DECIMAL(12,2),
    expense DECIMAL(12,2),
    balance DECIMAL(12,2)
);

SHOW TABLES;
DESC bank_flow;