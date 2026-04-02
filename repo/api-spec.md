# CEAMS API Specification

## `/api/v1/health/live`
### GET
**Summary**: Live

**Responses**:
- `200`: Successful Response

## `/api/v1/health/ready`
### GET
**Summary**: Ready

**Responses**:
- `200`: Successful Response

## `/api/v1/auth/login`
### POST
**Summary**: Login

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/auth/logout`
### POST
**Summary**: Logout

**Responses**:
- `200`: Successful Response

## `/api/v1/auth/me`
### GET
**Summary**: Me

**Responses**:
- `200`: Successful Response

## `/api/v1/auth/password/change`
### POST
**Summary**: Change Password

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/organizations`
### GET
**Summary**: List Organizations

**Responses**:
- `200`: Successful Response

### POST
**Summary**: Create Organization

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/organizations/{organization_id}`
### PUT
**Summary**: Update Organization

**Parameters**:
- `organization_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### DELETE
**Summary**: Delete Organization

**Parameters**:
- `organization_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/terms`
### GET
**Summary**: List Terms

**Responses**:
- `200`: Successful Response

### POST
**Summary**: Create Term

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/terms/{term_id}`
### PUT
**Summary**: Update Term

**Parameters**:
- `term_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### DELETE
**Summary**: Delete Term

**Parameters**:
- `term_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/courses`
### GET
**Summary**: List Courses

**Responses**:
- `200`: Successful Response

### POST
**Summary**: Create Course

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/courses/{course_id}`
### PUT
**Summary**: Update Course

**Parameters**:
- `course_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### DELETE
**Summary**: Delete Course

**Parameters**:
- `course_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/sections`
### GET
**Summary**: List Sections

**Responses**:
- `200`: Successful Response

### POST
**Summary**: Create Section

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/sections/{section_id}`
### PUT
**Summary**: Update Section

**Parameters**:
- `section_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### DELETE
**Summary**: Delete Section

**Parameters**:
- `section_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/registration-rounds`
### GET
**Summary**: List Rounds

**Responses**:
- `200`: Successful Response

### POST
**Summary**: Create Round

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/registration-rounds/{round_id}`
### PUT
**Summary**: Update Round

**Parameters**:
- `round_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### DELETE
**Summary**: Delete Round

**Parameters**:
- `round_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/users`
### GET
**Summary**: List Users

**Responses**:
- `200`: Successful Response

### POST
**Summary**: Create User

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/users/{user_id}`
### DELETE
**Summary**: Delete User

**Parameters**:
- `user_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### PUT
**Summary**: Update User

**Parameters**:
- `user_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/audit-log`
### GET
**Summary**: Get Audit Logs

**Parameters**:
- `entity_name` (unknown) in query: 
- `action` (unknown) in query: 
- `actor_id` (unknown) in query: 
- `limit` (integer) in query: 
- `offset` (integer) in query: 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/audit-log/retention`
### POST
**Summary**: Run Audit Log Retention

**Responses**:
- `200`: Successful Response

## `/api/v1/admin/scope-grants`
### POST
**Summary**: Create Scope Grant

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

### GET
**Summary**: List Scope Grants

**Parameters**:
- `user_id` (unknown) in query: 
- `scope_type` (unknown) in query: 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/admin/scope-grants/{grant_id}`
### DELETE
**Summary**: Delete Scope Grant

**Parameters**:
- `grant_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/courses`
### GET
**Summary**: List Courses

**Responses**:
- `200`: Successful Response

## `/api/v1/courses/{course_id}`
### GET
**Summary**: Get Course

**Parameters**:
- `course_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/courses/{course_id}/sections/{section_id}/eligibility`
### GET
**Summary**: Eligibility

**Parameters**:
- `course_id` (integer) in path (Required): 
- `section_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/registration/enroll`
### POST
**Summary**: Enroll

**Parameters**:
- `Idempotency-Key` (unknown) in header: 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/registration/waitlist`
### POST
**Summary**: Waitlist

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/registration/drop`
### POST
**Summary**: Drop

**Parameters**:
- `Idempotency-Key` (unknown) in header: 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/registration/status`
### GET
**Summary**: Registration Status

**Responses**:
- `200`: Successful Response

## `/api/v1/registration/history`
### GET
**Summary**: Registration History

**Responses**:
- `200`: Successful Response

## `/api/v1/reviews/forms`
### POST
**Summary**: Create Scoring Form

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rounds`
### POST
**Summary**: Create Round

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rounds/{round_id}/assignments/manual`
### POST
**Summary**: Manual Assign

**Parameters**:
- `round_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rounds/{round_id}/assignments/auto`
### POST
**Summary**: Auto Assign

**Parameters**:
- `round_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rounds/{round_id}/assignments`
### GET
**Summary**: List Assignments

**Parameters**:
- `round_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/scores`
### POST
**Summary**: Submit Score

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rounds/{round_id}/outliers`
### GET
**Summary**: List Outliers

**Parameters**:
- `round_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rounds/{round_id}/outliers/{flag_id}/resolve`
### POST
**Summary**: Resolve Outlier

**Parameters**:
- `round_id` (integer) in path (Required): 
- `flag_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rechecks`
### POST
**Summary**: Create Recheck

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rechecks/{recheck_id}/assign`
### POST
**Summary**: Assign Recheck

**Parameters**:
- `recheck_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rounds/{round_id}/close`
### POST
**Summary**: Close Round

**Parameters**:
- `round_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/reviews/rounds/{round_id}/export`
### GET
**Summary**: Export Round

**Parameters**:
- `round_id` (integer) in path (Required): 
- `format` (string) in query: 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/finance/accounts/{student_id}`
### GET
**Summary**: Get Account

**Parameters**:
- `student_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/finance/payments`
### POST
**Summary**: Post Payment

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/finance/prepayments`
### POST
**Summary**: Post Prepayment

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/finance/deposits`
### POST
**Summary**: Post Deposit

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/finance/refunds`
### POST
**Summary**: Post Refund

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/finance/month-end-billing`
### POST
**Summary**: Post Month End Billing

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/finance/arrears`
### GET
**Summary**: Get Arrears

**Responses**:
- `200`: Successful Response

## `/api/v1/finance/reconciliation/import`
### POST
**Summary**: Import Reconciliation

**Request Body**:
- `multipart/form-data`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/finance/reconciliation/{import_id}/report`
### GET
**Summary**: Get Reconciliation

**Parameters**:
- `import_id` (string) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/messaging/dispatch`
### POST
**Summary**: Dispatch

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/messaging/triggers`
### GET
**Summary**: List Triggers

**Responses**:
- `200`: Successful Response

## `/api/v1/messaging/triggers/{trigger_type}`
### PUT
**Summary**: Update Trigger

**Parameters**:
- `trigger_type` (string) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/messaging/triggers/process-due`
### POST
**Summary**: Process Due

**Responses**:
- `200`: Successful Response

## `/api/v1/messaging/notifications`
### GET
**Summary**: List Notifications

**Parameters**:
- `limit` (integer) in query: 
- `offset` (integer) in query: 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/messaging/notifications/{notification_id}/read`
### PATCH
**Summary**: Mark Notification Read

**Parameters**:
- `notification_id` (integer) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/data-quality/validate-write`
### POST
**Summary**: Validate Write

**Request Body**:
- `application/json`

**Responses**:
- `202`: Successful Response
- `422`: Validation Error

## `/api/v1/data-quality/quarantine`
### GET
**Summary**: List Quarantine

**Parameters**:
- `status` (unknown) in query: 
- `limit` (integer) in query: 
- `offset` (integer) in query: 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/data-quality/quarantine/{entry_id}/resolve`
### PATCH
**Summary**: Resolve Quarantine

**Parameters**:
- `entry_id` (integer) in path (Required): 

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/data-quality/report`
### GET
**Summary**: Get Report

**Responses**:
- `200`: Successful Response

## `/api/v1/integrations/clients`
### POST
**Summary**: Create Client

**Request Body**:
- `application/json`

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/integrations/clients/{client_id}/rotate-secret`
### POST
**Summary**: Rotate Client Secret

**Parameters**:
- `client_id` (string) in path (Required): 

**Responses**:
- `200`: Successful Response
- `422`: Validation Error

## `/api/v1/integrations/sis/students`
### POST
**Summary**: Sis Students Sync

**Responses**:
- `200`: Successful Response

## `/api/v1/integrations/qbank/forms`
### POST
**Summary**: Qbank Forms Import

**Responses**:
- `200`: Successful Response
