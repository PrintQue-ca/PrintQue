# API Routes Package
from flask import redirect, url_for, flash, jsonify, render_template
from .printers import register_printer_routes
from .orders import register_order_routes
from .system import register_misc_routes
from .license import register_license_routes
from .support import register_support_routes
from .history import register_history_routes
from services.state import get_ejection_paused, set_ejection_paused

__all__ = [
    'register_routes',
    'register_printer_routes',
    'register_order_routes', 
    'register_misc_routes',
    'register_license_routes',
    'register_support_routes',
    'register_history_routes',
]

def register_routes(app, socketio):
    register_printer_routes(app, socketio)
    register_order_routes(app, socketio)
    register_misc_routes(app, socketio)
    register_license_routes(app, socketio)
    register_support_routes(app, socketio)
    register_history_routes(app, socketio)
    
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
            from services.printer_manager import trigger_mass_ejection_for_finished_printers
            
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
    
    # API v1 routes for React frontend
    @app.route('/api/v1/ejection/status', methods=['GET'])
    def api_ejection_status():
        """API: Get current ejection status"""
        return jsonify({
            'paused': get_ejection_paused(),
            'status': 'paused' if get_ejection_paused() else 'active'
        })
    
    @app.route('/api/v1/ejection/pause', methods=['POST'])
    def api_pause_ejection():
        """API: Pause ejection globally"""
        try:
            set_ejection_paused(True)
            return jsonify({'success': True, 'message': 'Ejection paused globally'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/v1/ejection/resume', methods=['POST'])
    def api_resume_ejection():
        """API: Resume ejection globally"""
        try:
            set_ejection_paused(False)
            from services.printer_manager import trigger_mass_ejection_for_finished_printers
            ejection_count = trigger_mass_ejection_for_finished_printers(socketio, app)
            return jsonify({
                'success': True, 
                'message': 'Ejection resumed globally',
                'printers_ejecting': ejection_count
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
