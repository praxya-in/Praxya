SET LOCAL role = authenticated;
SET LOCAL "request.jwt.claims" = '{"sub": "507429fb-5f07-4309-b14e-cfbf2c6724e6"}';
SELECT id, name FROM facilities;