CREATE TABLE test_data (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO test_data (name) VALUES
    ('Test data 1'),
    ('Test data 2'),
    ('Test data 3'); 