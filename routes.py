from flask import redirect, url_for, flash, jsonify, render_template
from printer_routes import register_printer_routes
from order_routes import register_order_routes
from misc_routes import register_misc_routes
from license_routes import register_license_routes
from support_routes import register_support_routes
from history_routes import register_history_routes  # Add this import
from state import get_ejection_paused, set_ejection_paused

def register_routes(app, socketio):
    register_printer_routes(app, socketio)
    register_order_routes(app, socketio)
    register_misc_routes(app, socketio)
    register_license_routes(app, socketio)
    register_support_routes(app, socketio)
    register_history_routes(app, socketio)  # Add this line
    
    # Ejection control routes
    @app.route('/pause_ejection', methods=['POST'])
    def pause_ejection():
        """Pause ejection globally"""
        try:
            set_ejection_paused(True)
            flash("✅ Ejection paused globally. Completed prints will remain in FINISHED state.", "success")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"❌ Error pausing ejection: {str(e)}", "error")
            return redirect(url_for('index'))

    @app.route('/resume_ejection', methods=['POST'])
    def resume_ejection():
        """Resume ejection globally"""
        try:
            set_ejection_paused(False)
            
            # Import here to avoid circular imports
            from printer_manager import trigger_mass_ejection_for_finished_printers
            
            # Trigger mass ejection for all waiting FINISHED printers
            ejection_count = trigger_mass_ejection_for_finished_printers(socketio, app)
            
            if ejection_count > 0:
                flash(f"✅ Ejection resumed globally. {ejection_count} printers now ejecting.", "success")
            else:
                flash("✅ Ejection resumed globally. No printers were waiting for ejection.", "success")
            
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"❌ Error resuming ejection: {str(e)}", "error")
            return redirect(url_for('index'))

    @app.route('/ejection_status', methods=['GET'])
    def ejection_status():
        """Get current ejection status"""
        return jsonify({
            'paused': get_ejection_paused(),
            'status': 'paused' if get_ejection_paused() else 'active'
        })