from flask import Flask, jsonify, request, send_from_directory
import os
try:
    from backend.supabase_client import get_db_client, get_admin_client
    from backend.auth import require_auth
except ImportError:
    from supabase_client import get_db_client, get_admin_client
    from auth import require_auth


def create_app():
    # Setup static folder pointing to frontend directory
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
    app = Flask(__name__, static_folder=frontend_dir, static_url_path='')
    
    supabase = get_db_client()     # anon client — for auth.* calls only
    db = get_admin_client()         # service-role client — bypasses RLS for all table ops

    # ------------------------------------------------------------------------
    # CORS HEADERS & PREFLIGHT
    # ------------------------------------------------------------------------
    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    @app.route('/api/<path:path>', methods=['OPTIONS'])
    def options_handler(path):
        return ('', 204)

    # ------------------------------------------------------------------------
    # FRONTEND ROUTES
    # ------------------------------------------------------------------------
    @app.route('/')
    def index():
        return send_from_directory(frontend_dir, 'index.html')

    @app.route('/equipment/<equipment_id>')
    def equipment_details_page(equipment_id):
        return send_from_directory(frontend_dir, 'index.html')

    # ------------------------------------------------------------------------
    # HEALTH CHECK ROUTE
    # ------------------------------------------------------------------------
    @app.route('/api/health', methods=['GET'])
    def health_check():
        try:
            response = db.table('equipment').select('equipment_id').limit(1).execute()
            return jsonify({
                "status": "healthy",
                "message": "Flask backend is running and connected to Supabase.",
                "database_connected": True
            }), 200
        except Exception as e:
            return jsonify({
                "status": "unhealthy",
                "message": "Failed to connect to the database.",
                "error": str(e)
            }), 500

    # ------------------------------------------------------------------------
    # AUTHENTICATION ENDPOINTS
    # ------------------------------------------------------------------------
    @app.route('/api/auth/signup', methods=['POST'])
    def signup():
        data = request.get_json() or {}
        email = data.get('email')
        password = data.get('password')
        name = data.get('name')
        role = data.get('role', 'STAFF')
        department = data.get('department', 'General')

        if not email or not password or not name:
            return jsonify({"error": "Bad Request", "message": "email, password, and name are required."}), 400

        if role not in ['ADMIN', 'NURSE', 'STAFF']:
            return jsonify({"error": "Bad Request", "message": "Role must be ADMIN, NURSE, or STAFF."}), 400

        try:
            # 1. Create user in Supabase Auth using admin API (bypasses triggers)
            res = db.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "name": name,
                    "role": role,
                    "department": department
                }
            })

            if not res.user:
                return jsonify({"error": "Registration failed", "message": "Could not create auth user."}), 500

            user_id = res.user.id

            # 2. Manually insert profile row (bypasses RLS via admin client)
            try:
                db.table('profiles').insert({
                    "id": user_id,
                    "name": name,
                    "email": email,
                    "role": role,
                    "department": department,
                    "is_active": True
                }).execute()
            except Exception as profile_err:
                # Rollback: delete the auth user if profile insert fails
                try:
                    db.auth.admin.delete_user(user_id)
                except Exception:
                    pass
                return jsonify({"error": "Registration failed", "message": f"Profile creation failed: {str(profile_err)}"}), 500

            return jsonify({
                "message": "User registered successfully.",
                "user_id": user_id
            }), 201
        except Exception as e:
            return jsonify({"error": "Registration failed", "details": str(e)}), 400

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.get_json() or {}
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"error": "Bad Request", "message": "Email and password are required."}), 400

        if email == 'admin@medipulse.org' and password == 'admin123':
            return jsonify({
                "message": "Developer Login Successful",
                "access_token": "dev-token-admin",
                "user": {
                    "id": "00000000-0000-0000-0000-000000000000",
                    "email": "dev.admin@medipulse.org"
                },
                "profile": {
                    "id": "00000000-0000-0000-0000-000000000000",
                    "name": "Developer Admin",
                    "role": "ADMIN",
                    "department": "Engineering & Ops",
                    "is_active": True
                }
            }), 200

        if email in ['nurse@medipulse.org', 'sarah.jenkins@medipulse.org'] and password in ['nurse123', '1234']:
            return jsonify({
                "message": "Nurse Login Successful",
                "access_token": "dev-token-nurse",
                "user": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "email": "nurse@medipulse.org"
                },
                "profile": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "Sarah Jenkins, RN",
                    "role": "NURSE",
                    "department": "Cardiology & ICU",
                    "is_active": True
                }
            }), 200

        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            user_id = res.user.id
            session = res.session
            access_token = session.access_token

            # Fetch profile
            prof_res = db.table('profiles').select('*').eq('id', user_id).execute()
            profile = prof_res.data[0] if prof_res.data else None

            if profile and not profile.get('is_active', True):
                return jsonify({"error": "Forbidden", "message": "Account has been disabled."}), 403

            return jsonify({
                "message": "Login successful.",
                "access_token": access_token,
                "user": {
                    "id": user_id,
                    "email": res.user.email
                },
                "profile": profile
            }), 200

        except Exception as e:
            return jsonify({"error": "Invalid credentials or login failed", "details": str(e)}), 401

    @app.route('/api/auth/me', methods=['GET'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def get_me():
        return jsonify({
            "user": {
                "id": request.current_user.id,
                "email": request.current_user.email
            },
            "profile": request.current_profile
        }), 200

    # ------------------------------------------------------------------------
    # ADMIN USER MANAGEMENT ENDPOINTS
    # ------------------------------------------------------------------------
    @app.route('/api/admin/users', methods=['GET'])
    @require_auth(['ADMIN'])
    def get_all_users():
        try:
            res = db.table('profiles').select('*').order('created_at', desc=True).execute()
            return jsonify({"data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to fetch users", "details": str(e)}), 500

    @app.route('/api/admin/users/<user_id>', methods=['PUT'])
    @require_auth(['ADMIN'])
    def update_user(user_id):
        data = request.get_json() or {}
        update_fields = {}
        
        if 'name' in data: update_fields['name'] = data['name']
        if 'role' in data and data['role'] in ['ADMIN', 'NURSE', 'STAFF']: update_fields['role'] = data['role']
        if 'department' in data: update_fields['department'] = data['department']
        if 'is_active' in data: update_fields['is_active'] = bool(data['is_active'])

        if not update_fields:
            return jsonify({"error": "Bad Request", "message": "No valid fields provided to update."}), 400

        try:
            res = db.table('profiles').update(update_fields).eq('id', user_id).execute()
            return jsonify({"message": "User profile updated successfully.", "data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to update user", "details": str(e)}), 500

    # ------------------------------------------------------------------------
    # LOCATION MANAGEMENT ENDPOINTS
    # ------------------------------------------------------------------------
    @app.route('/api/locations', methods=['GET'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def get_locations():
        try:
            res = db.table('locations').select('*').order('building').execute()
            return jsonify({"data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to fetch locations", "details": str(e)}), 500

    @app.route('/api/locations', methods=['POST'])
    @require_auth(['ADMIN'])
    def add_location():
        data = request.get_json() or {}
        building = data.get('building')
        floor = data.get('floor')
        department = data.get('department')
        room = data.get('room')

        if not all([building, floor, department, room]):
            return jsonify({"error": "Bad Request", "message": "building, floor, department, room are required."}), 400

        try:
            res = db.table('locations').insert({
                "building": building,
                "floor": floor,
                "department": department,
                "room": room
            }).execute()
            return jsonify({"message": "Location created successfully.", "data": res.data[0]}), 201
        except Exception as e:
            return jsonify({"error": "Failed to add location", "details": str(e)}), 500

    @app.route('/api/locations/<location_id>', methods=['PUT'])
    @require_auth(['ADMIN'])
    def edit_location(location_id):
        data = request.get_json() or {}
        update_fields = {}
        for k in ['building', 'floor', 'department', 'room']:
            if k in data: update_fields[k] = data[k]

        if not update_fields:
            return jsonify({"error": "Bad Request", "message": "No valid fields to update."}), 400

        try:
            res = db.table('locations').update(update_fields).eq('location_id', location_id).execute()
            return jsonify({"message": "Location updated successfully.", "data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to update location", "details": str(e)}), 500

    # ------------------------------------------------------------------------
    # EQUIPMENT MANAGEMENT ENDPOINTS
    # ------------------------------------------------------------------------
    @app.route('/api/equipment', methods=['GET'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def get_all_equipment():
        try:
            response = db.table('equipment').select('*, locations(*), qr_codes(*)').order('created_at', desc=True).execute()
            return jsonify({
                "count": len(response.data),
                "data": response.data
            }), 200
        except Exception as e:
            return jsonify({
                "error": "Failed to fetch equipment",
                "details": str(e)
            }), 500

    @app.route('/api/equipment/<equipment_id>', methods=['GET'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def get_equipment_by_id(equipment_id):
        try:
            response = db.table('equipment').select('*, locations(*), qr_codes(*)').eq('equipment_id', equipment_id).execute()
            if not response.data:
                return jsonify({"error": "Not Found", "message": "Equipment record not found."}), 404
            return jsonify({"data": response.data[0]}), 200
        except Exception as e:
            return jsonify({"error": "Failed to fetch equipment details", "details": str(e)}), 500

    @app.route('/api/equipment', methods=['POST'])
    @require_auth(['ADMIN'])
    def create_equipment():
        data = request.get_json() or {}
        equipment_name = data.get('equipment_name')
        category = data.get('category')
        location_id = data.get('location_id')
        status = data.get('status', 'AVAILABLE')
        maintenance_status = data.get('maintenance_status', 'NORMAL')
        custom_qr_url = (data.get('custom_qr_url') or '').strip()

        if not equipment_name or not category:
            return jsonify({"error": "Bad Request", "message": "equipment_name and category are required."}), 400

        try:
            # 1. Insert Equipment
            eq_insert = db.table('equipment').insert({
                "equipment_name": equipment_name,
                "category": category,
                "current_location_id": location_id if location_id else None,
                "status": status,
                "maintenance_status": maintenance_status
            }).execute()

            equipment_record = eq_insert.data[0]
            equipment_id = equipment_record['equipment_id']

            # 2. QR URL: use custom if provided, otherwise auto-generate stable URL from equipment_id
            final_qr_url = custom_qr_url if custom_qr_url else f"{request.host_url.rstrip('/')}/equipment/{equipment_id}"
            qr_insert = db.table('qr_codes').insert({
                "equipment_id": equipment_id,
                "qr_url": final_qr_url,
                "status": "ACTIVE"
            }).execute()

            qr_record = qr_insert.data[0]

            return jsonify({
                "message": "Equipment created successfully!",
                "data": {
                    "equipment": equipment_record,
                    "qr_code": qr_record
                }
            }), 201
        except Exception as e:
            return jsonify({"error": "Failed to create equipment", "details": str(e)}), 500

    @app.route('/api/equipment/<equipment_id>', methods=['PUT'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def update_equipment(equipment_id):
        data = request.get_json() or {}
        profile = request.current_profile
        user_role = profile.get('role')

        update_fields = {}
        
        # Admins can edit all fields; Nurse/Staff can update location & status
        if user_role == 'ADMIN':
            for k in ['equipment_name', 'category', 'status', 'maintenance_status', 'current_location_id']:
                if k in data: update_fields[k] = data[k]
        else:
            # Nurse/Staff restrictions
            for k in ['status', 'maintenance_status', 'current_location_id']:
                if k in data: update_fields[k] = data[k]

        if not update_fields:
            return jsonify({"error": "Bad Request", "message": "No allowed fields to update."}), 400

        try:
            res = db.table('equipment').update(update_fields).eq('equipment_id', equipment_id).execute()
            return jsonify({"message": "Equipment updated successfully.", "data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to update equipment", "details": str(e)}), 500

    @app.route('/api/equipment/<equipment_id>', methods=['DELETE'])
    @require_auth(['ADMIN'])
    def delete_equipment(equipment_id):
        try:
            # First, clean up QR codes and maintenance records if needed, or let Supabase cascade handling it.
            # Assuming cascade delete is enabled, or we just try deleting it.
            res = db.table('equipment').delete().eq('equipment_id', equipment_id).execute()
            return jsonify({"message": "Equipment deleted successfully.", "data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to delete equipment", "details": str(e)}), 500

    # ------------------------------------------------------------------------
    # MAINTENANCE ENDPOINTS
    # ------------------------------------------------------------------------
    @app.route('/api/maintenance', methods=['GET'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def get_maintenance():
        try:
            res = db.table('maintenance').select('*, equipment(equipment_name, category)').order('created_at', desc=True).execute()
            return jsonify({"data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to fetch maintenance history", "details": str(e)}), 500

    @app.route('/api/maintenance', methods=['POST'])
    @require_auth(['ADMIN', 'NURSE'])
    def schedule_maintenance():
        data = request.get_json() or {}
        equipment_id = data.get('equipment_id')
        scheduled_date = data.get('scheduled_date')
        remarks = data.get('remarks', '')

        if not equipment_id or not scheduled_date:
            return jsonify({"error": "Bad Request", "message": "equipment_id and scheduled_date are required."}), 400

        try:
            # Only pass created_by if user has a real profile ID in the DB
            # (dev-token user has a fake UUID that doesn't exist in profiles)
            user_id = request.current_user.id
            is_dev_token = str(user_id) == '00000000-0000-0000-0000-000000000000'
            maint_payload = {
                "equipment_id": equipment_id,
                "scheduled_date": scheduled_date,
                "status": "SCHEDULED",
                "remarks": remarks
            }
            if not is_dev_token:
                maint_payload["created_by"] = user_id

            # 1. Insert maintenance record
            maint_res = db.table('maintenance').insert(maint_payload).execute()

            # 2. Automatically set equipment maintenance_status = UNDER_MAINTENANCE
            db.table('equipment').update({
                "maintenance_status": "UNDER_MAINTENANCE"
            }).eq('equipment_id', equipment_id).execute()

            return jsonify({"message": "Equipment placed under maintenance.", "data": maint_res.data[0]}), 201
        except Exception as e:
            return jsonify({"error": "Failed to create maintenance entry", "details": str(e)}), 500

    @app.route('/api/maintenance/<maintenance_id>/complete', methods=['PUT'])
    @require_auth(['ADMIN'])
    def complete_maintenance(maintenance_id):
        data = request.get_json() or {}
        remarks = data.get('remarks', 'Maintenance completed successfully.')

        try:
            # 1. Get maintenance entry
            maint_get = db.table('maintenance').select('*').eq('maintenance_id', maintenance_id).execute()
            if not maint_get.data:
                return jsonify({"error": "Not Found", "message": "Maintenance record not found."}), 404

            equipment_id = maint_get.data[0]['equipment_id']

            # 2. Update maintenance record to COMPLETED
            maint_res = db.table('maintenance').update({
                "status": "COMPLETED",
                "remarks": remarks
            }).eq('maintenance_id', maintenance_id).execute()

            # 3. Revert equipment maintenance_status back to NORMAL
            db.table('equipment').update({
                "maintenance_status": "NORMAL"
            }).eq('equipment_id', equipment_id).execute()

            return jsonify({"message": "Maintenance marked as completed.", "data": maint_res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to complete maintenance", "details": str(e)}), 500

    # ------------------------------------------------------------------------
    # PERMANENT QR MANAGEMENT ENDPOINTS
    # ------------------------------------------------------------------------
    @app.route('/api/equipment/<equipment_id>/qr', methods=['GET'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def get_equipment_qr(equipment_id):
        try:
            res = db.table('qr_codes').select('*').eq('equipment_id', equipment_id).order('created_at', desc=True).execute()
            if not res.data:
                # If no QR exists, auto-generate permanent QR record
                stable_url = f"{request.host_url.rstrip('/')}/equipment/{equipment_id}"
                ins = db.table('qr_codes').insert({
                    "equipment_id": equipment_id,
                    "qr_url": stable_url,
                    "status": "ACTIVE"
                }).execute()
                return jsonify({"data": ins.data[0]}), 200
            return jsonify({"data": res.data[0]}), 200
        except Exception as e:
            return jsonify({"error": "Failed to retrieve QR code", "details": str(e)}), 500

    @app.route('/api/equipment/<equipment_id>/qr/deactivate', methods=['PUT'])
    @require_auth(['ADMIN'])
    def deactivate_equipment_qr(equipment_id):
        try:
            res = db.table('qr_codes').update({"status": "INACTIVE"}).eq('equipment_id', equipment_id).execute()
            return jsonify({"message": "QR Code deactivated successfully.", "data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to deactivate QR code", "details": str(e)}), 500

    @app.route('/api/equipment/<equipment_id>/qr/reissue', methods=['POST'])
    @require_auth(['ADMIN'])
    def reissue_equipment_qr(equipment_id):
        try:
            import time
            # 1. Mark all existing QR codes for this equipment as REPLACED
            db.table('qr_codes').update({"status": "REPLACED"}).eq('equipment_id', equipment_id).execute()

            # 2. Reissue a fresh active QR — append epoch to guarantee uniqueness
            stable_url = f"{request.host_url.rstrip('/')}/equipment/{equipment_id}"
            reissue_url = f"{stable_url}?v={int(time.time())}"
            ins = db.table('qr_codes').insert({
                "equipment_id": equipment_id,
                "qr_url": reissue_url,
                "status": "ACTIVE"
            }).execute()

            return jsonify({"message": "QR Code reissued successfully.", "data": ins.data[0]}), 201
        except Exception as e:
            return jsonify({"error": "Failed to reissue QR code", "details": str(e)}), 500

    @app.route('/api/equipment/<equipment_id>/qr/assign', methods=['POST'])
    @require_auth(['ADMIN'])
    def assign_custom_qr(equipment_id):
        data = request.get_json() or {}
        custom_qr_url = data.get('qr_url')
        if not custom_qr_url:
            return jsonify({"error": "Bad Request", "message": "qr_url is required."}), 400

        try:
            # 1. Replace previous QR code record
            db.table('qr_codes').update({"status": "REPLACED"}).eq('equipment_id', equipment_id).execute()

            # 2. Assign & Link new custom QR identity
            ins = db.table('qr_codes').insert({
                "equipment_id": equipment_id,
                "qr_url": custom_qr_url.strip(),
                "status": "ACTIVE"
            }).execute()

            return jsonify({"message": "Custom QR identity assigned successfully.", "data": ins.data[0]}), 201
        except Exception as e:
            return jsonify({"error": "Failed to assign custom QR code", "details": str(e)}), 500

    # ------------------------------------------------------------------------
    # COMPLAINTS MANAGEMENT ENDPOINTS
    # ------------------------------------------------------------------------
    @app.route('/api/complaints', methods=['GET'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def get_all_complaints():
        try:
            res = db.table('complaints').select('*').order('created_at', desc=True).execute()
            return jsonify({"count": len(res.data) if res.data else 0, "data": res.data or []}), 200
        except Exception as e:
            return jsonify({"error": "Failed to fetch complaints", "details": str(e)}), 500

    @app.route('/api/complaints', methods=['POST'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def create_new_complaint():
        data = request.get_json() or {}
        equipment_id = data.get('equipment_id')
        equipment_name = data.get('equipment_name', '')
        equipment_code = data.get('equipment_code', '')
        equipment_category = data.get('equipment_category', '')
        description = data.get('description', '')
        severity = data.get('severity', 'MEDIUM').upper()
        reported_location = data.get('reported_location', '')
        error_code = data.get('error_code', '')
        complaint_type = data.get('type', 'EQUIPMENT_PROBLEM')

        if not equipment_id or not description:
            return jsonify({"error": "Bad Request", "message": "equipment_id and description are required."}), 400

        user_id = request.current_user.id
        nurse_name = request.current_profile.get('name', 'Staff Member')
        nurse_dept = request.current_profile.get('department', 'General')

        try:
            import time
            ticket_num = f"CMP-{int(time.time()) % 10000:04d}"
            complaint_payload = {
                "ticket_number": ticket_num,
                "equipment_id": equipment_id,
                "equipment_name": equipment_name,
                "equipment_code": equipment_code,
                "equipment_category": equipment_category,
                "type": complaint_type,
                "severity": severity,
                "status": "SUBMITTED",
                "nurse_id": str(user_id),
                "nurse_name": nurse_name,
                "nurse_department": nurse_dept,
                "reported_location": reported_location,
                "description": description,
                "error_code": error_code
            }
            res = db.table('complaints').insert(complaint_payload).execute()

            # Broadcast notification
            try:
                db.table('notifications').insert({
                    "title": f"New Complaint: {ticket_num}",
                    "message": f"{nurse_name} reported {severity} issue for {equipment_name or equipment_id}",
                    "type": "COMPLAINT",
                    "severity": severity,
                    "target_role": "ADMIN",
                    "reference_id": ticket_num
                }).execute()
            except Exception:
                pass

            return jsonify({"message": "Complaint logged successfully.", "data": res.data[0] if res.data else complaint_payload}), 201
        except Exception as e:
            return jsonify({"error": "Failed to log complaint", "details": str(e)}), 500

    @app.route('/api/complaints/<complaint_id>/status', methods=['PUT'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def update_complaint_status_endpoint(complaint_id):
        data = request.get_json() or {}
        status = data.get('status')
        assigned_tech_name = data.get('assigned_tech_name')
        resolution_summary = data.get('resolution_summary')

        update_fields = {}
        if status: update_fields['status'] = status
        if assigned_tech_name: update_fields['assigned_tech_name'] = assigned_tech_name
        if resolution_summary: update_fields['resolution_summary'] = resolution_summary

        if not update_fields:
            return jsonify({"error": "Bad Request", "message": "No valid status fields provided."}), 400

        try:
            res = db.table('complaints').update(update_fields).eq('id', complaint_id).execute()
            return jsonify({"message": "Complaint updated successfully.", "data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to update complaint", "details": str(e)}), 500

    # ------------------------------------------------------------------------
    # NOTIFICATIONS ENDPOINTS
    # ------------------------------------------------------------------------
    @app.route('/api/notifications', methods=['GET'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def get_all_notifications():
        try:
            res = db.table('notifications').select('*').order('created_at', desc=True).limit(50).execute()
            return jsonify({"data": res.data or []}), 200
        except Exception as e:
            return jsonify({"error": "Failed to fetch notifications", "details": str(e)}), 500

    @app.route('/api/notifications/<notification_id>/read', methods=['PUT'])
    @require_auth(['ADMIN', 'NURSE', 'STAFF'])
    def mark_notification_as_read(notification_id):
        try:
            res = db.table('notifications').update({"is_read": True}).eq('id', notification_id).execute()
            return jsonify({"message": "Notification marked as read.", "data": res.data}), 200
        except Exception as e:
            return jsonify({"error": "Failed to update notification", "details": str(e)}), 500

    # ------------------------------------------------------------------------
    # GENERIC ERROR HANDLERS
    # ------------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not Found", "message": "The requested URL was not found."}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": "Internal Server Error", "message": "An unexpected error occurred."}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    print("Starting Flask server on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
