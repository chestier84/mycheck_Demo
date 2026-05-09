BEGIN
  FOR i IN 1..100 LOOP
    INSERT INTO PRueba (id, nombre) VALUES (i, 'Registro_' || i);
  END LOOP;
  COMMIT;
END;
/
