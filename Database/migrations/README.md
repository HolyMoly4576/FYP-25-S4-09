# Database Migrations

This folder contains database migration scripts for updating existing database schemas.

## Current Status

**Note:** SYSADMIN support has been added directly to the base `Database.sql` schema file. 
If you are setting up a new database, use `Database.sql` which already includes SYSADMIN support.

## For Existing Databases

If you have an existing database that was created before SYSADMIN support was added, you will need to manually update the constraint:

```sql
-- Drop the existing constraint
ALTER TABLE account 
DROP CONSTRAINT IF EXISTS check_account_type;

-- Add the new constraint with SYSADMIN support
ALTER TABLE account
ADD CONSTRAINT check_account_type 
CHECK (type IN ('FREE', 'PAID', 'SYSADMIN'));
```

## Future Migrations

Future database schema changes can be added as migration scripts in this folder.
