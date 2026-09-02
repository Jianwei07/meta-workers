ALTER TABLE messages ADD COLUMN response_items_json TEXT;

UPDATE agents SET model = 'gpt-5.6' WHERE model = 'grok-4.3';
