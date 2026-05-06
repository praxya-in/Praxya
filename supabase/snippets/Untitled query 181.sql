-- Check what RLS policies exist on facilities
SELECT policyname, cmd, qual 
FROM pg_policies 
WHERE tablename = 'facilities';