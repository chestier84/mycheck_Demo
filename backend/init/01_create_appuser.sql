-- =============================================================================
--  Script de inicialización: crea el usuario appuser utilizado por el sistema
--  Datafix Oracle Automático.
--
--  Se ejecuta automáticamente la primera vez que levanta el contenedor Oracle XE
--  porque lo montamos en /opt/oracle/scripts/startup/
-- =============================================================================
ALTER SESSION SET CONTAINER = XEPDB1;

CREATE USER appuser IDENTIFIED BY "app123"
  DEFAULT TABLESPACE USERS
  TEMPORARY TABLESPACE TEMP
  QUOTA UNLIMITED ON USERS;

GRANT CONNECT, RESOURCE TO appuser;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE PROCEDURE TO appuser;
GRANT SELECT ANY DICTIONARY TO appuser;
GRANT SELECT_CATALOG_ROLE TO appuser;

-- Tablas de ejemplo para pruebas
CREATE TABLE appuser.employees (
  employee_id   NUMBER PRIMARY KEY,
  first_name    VARCHAR2(50),
  last_name     VARCHAR2(50),
  salary        NUMBER(10,2),
  hire_date     DATE DEFAULT SYSDATE,
  department_id NUMBER
);

INSERT INTO appuser.employees VALUES (101,'Ana','García',1500000,DATE '2019-03-15',50);
INSERT INTO appuser.employees VALUES (102,'Luis','Pérez',1800000,DATE '2018-07-20',50);
INSERT INTO appuser.employees VALUES (103,'María','López',2100000,DATE '2020-11-01',60);
COMMIT;

CREATE TABLE appuser.audit_log (
  id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  action     VARCHAR2(100),
  exec_date  TIMESTAMP DEFAULT SYSTIMESTAMP,
  username   VARCHAR2(50)
);

EXIT;
