-- Database Views for User Profiles and Account Management
-- These views provide cleaner, organized access to user and account data

-- View: User Account Summary
-- Provides a clean view of all accounts with their basic information
CREATE OR REPLACE VIEW user_account_summary AS
SELECT 
    account_id,
    username,
    email,
    type AS account_type,
    created_at,
    CASE 
        WHEN type = 'FREE' THEN 'Free account with limited storage'
        WHEN type = 'PAID' THEN 'Paid account with extended storage and features'
        WHEN type = 'SYSADMIN' THEN 'System administrator account'
        ELSE 'Unknown account type'
    END AS account_description
FROM account;

-- View: Free Account Details
-- Shows free accounts with their storage limits
CREATE OR REPLACE VIEW free_account_details AS
SELECT 
    a.account_id,
    a.username,
    a.email,
    a.created_at,
    fa.storage_limit_gb,
    'Free account with limited storage' AS description
FROM account a
INNER JOIN free_account fa ON a.account_id = fa.account_id
WHERE a.type = 'FREE';

-- View: Paid Account Details
-- Shows paid accounts with their subscription information
CREATE OR REPLACE VIEW paid_account_details AS
SELECT 
    a.account_id,
    a.username,
    a.email,
    a.created_at,
    pa.storage_limit_gb,
    pa.monthly_cost,
    pa.start_date,
    pa.renewal_date,
    pa.end_date,
    pa.status,
    'Paid account with extended storage and features' AS description
FROM account a
INNER JOIN paid_account pa ON a.account_id = pa.account_id
WHERE a.account_type = 'PAID';

-- View: Account Profile Types
-- Lists all available account types (can be used by the API endpoint)
-- Note: This is a reference view that matches the userprofiles API endpoint
CREATE OR REPLACE VIEW account_profile_types AS
SELECT DISTINCT
    type AS profile_type,
    CASE 
        WHEN type = 'FREE' THEN 'Free account with limited storage'
        WHEN type = 'PAID' THEN 'Paid account with extended storage and features'
        WHEN type = 'SYSADMIN' THEN 'System administrator account'
        ELSE 'Unknown account type'
    END AS description,
    CASE 
        WHEN type IN ('FREE', 'PAID') THEN 'user'
        WHEN type = 'SYSADMIN' THEN 'sysadmin'
        ELSE 'user'
    END AS login_interface
FROM account
WHERE type IN ('FREE', 'PAID', 'SYSADMIN');

-- Note: The userprofiles API endpoint is available at:
-- GET http://localhost:8000/userprofiles
-- This endpoint returns the available user profile types for the login dropdown

