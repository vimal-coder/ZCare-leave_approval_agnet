-- ==========================================
-- EMPLOYEES TABLE
-- ==========================================

CREATE TABLE employees (
    employee_id SERIAL PRIMARY KEY,
    employee_code VARCHAR(20) UNIQUE NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    department VARCHAR(100),
    manager_email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



-- ==========================================
-- LEAVE BALANCES
-- ==========================================

CREATE TABLE leave_balances (
    balance_id SERIAL PRIMARY KEY,

    employee_id INT UNIQUE NOT NULL,

    annual_leave INT DEFAULT 15,
    personal_leave INT DEFAULT 8,
    special_leave INT DEFAULT 5,
    optional_holiday INT DEFAULT 2,

    FOREIGN KEY (employee_id)
    REFERENCES employees(employee_id)
);

-- ==========================================
-- LEAVE REQUESTS
-- ==========================================

CREATE TABLE leave_requests (

    request_id SERIAL PRIMARY KEY,

    employee_id INT NOT NULL,

    leave_type VARCHAR(50) NOT NULL,

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    total_days INT NOT NULL,

    reason TEXT,

    applied_date DATE DEFAULT CURRENT_DATE,

    notice_period INT,

    is_exceptional BOOLEAN DEFAULT FALSE,

    is_lop BOOLEAN DEFAULT FALSE,

    status VARCHAR(30)
    CHECK (
        status IN (
            'AUTO_APPROVED',
            'PENDING',
            'APPROVED',
            'REJECTED',
            'LOP',
            'ESCALATED'
        )
    ),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (employee_id)
    REFERENCES employees(employee_id)
);



-- ==========================================
-- EXCEPTIONAL CASES
-- ==========================================

CREATE TABLE exceptional_cases (

    exception_id SERIAL PRIMARY KEY,

    employee_id INT NOT NULL,

    request_id INT NOT NULL,

    exception_year INT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (employee_id)
    REFERENCES employees(employee_id),

    FOREIGN KEY (request_id)
    REFERENCES leave_requests(request_id)
);



-- ==========================================
-- MANAGER APPROVALS
-- ==========================================

CREATE TABLE manager_approvals (

    approval_id SERIAL PRIMARY KEY,

    request_id INT NOT NULL,

    manager_email VARCHAR(100),

    decision VARCHAR(20)
    CHECK (
        decision IN (
            'APPROVED',
            'REJECTED'
        )
    ),

    comments TEXT,

    approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (request_id)
    REFERENCES leave_requests(request_id)
);


-- ==========================================
-- EMAIL LOGS
-- ==========================================

CREATE TABLE email_logs (

    email_id SERIAL PRIMARY KEY,

    request_id INT,

    recipient_email VARCHAR(100),

    subject VARCHAR(255),

    email_status VARCHAR(20)
    CHECK (
        email_status IN (
            'SENT',
            'FAILED'
        )
    ),

    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (request_id)
    REFERENCES leave_requests(request_id)
);

-- ==========================================
-- SAMPLE EMPLOYEES
-- ==========================================

INSERT INTO employees
(
employee_code,
employee_name,
email,
department,
manager_email
)
VALUES

(
'E001',
'Rahul Kumar',
'rahul@gmail.com',
'Nurse',
'vv366204@gmail.com'
),

(
'E002',
'Praveen',
'spraveenthampi@gmail.com',
'Finance',
'vv366204@gmail.com'
),

(
'E003',
'Vimal',
'vimal0162003@gmail.com',
'Worker',
'vv366204@gmail.com'
);
INSERT INTO leave_balances
(
employee_id,
annual_leave,
personal_leave,
special_leave,
optional_holiday
)
VALUES

(1,15,8,5,2),
(2,10,8,5,2),
(3,0,8,5,2);
SELECT * FROM employees;
SELECT * FROM leave_balances;
SELECT * FROM leave_requests;
SELECT * FROM exceptional_cases;
SELECT * FROM manager_approvals;
SELECT * FROM email_logs;