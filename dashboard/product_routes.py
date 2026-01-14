"""
Product Management Routes
Handles saving, editing, and managing products for campaigns
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from core.database import Database
from bson import ObjectId
import traceback

product_bp = Blueprint('products', __name__, url_prefix='/products')
db = Database()

def verify_product_ownership(product_id: str) -> tuple:
    """Verify that the current user owns the product"""
    try:
        product = db.get_product(product_id)
        if not product:
            return False, None, None
        
        # Get user's MongoDB _id
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_doc = db.get_user_by_discord_id_sync(discord_id)
        
        if not user_doc:
            return False, product, None
        
        user_mongo_id = str(user_doc['_id'])
        product_user_id = str(product.get('user_id', ''))
        
        is_owner = (product_user_id == user_mongo_id)
        return is_owner, product, user_mongo_id
    except Exception as e:
        print(f"Error verifying product ownership: {e}")
        traceback.print_exc()
        return False, None, None

@product_bp.route('/')
@login_required
def products_list():
    """List all products for the current user"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        products = db.get_user_products(discord_id)
        
        return render_template('modern/products.html',
                             products=products,
                             total_products=len(products))
    except Exception as e:
        print(f"Error loading products: {e}")
        traceback.print_exc()
        flash('Error loading products', 'error')
        return render_template('modern/products.html', products=[], total_products=0)

@product_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_product():
    """Create a new product"""
    if request.method == 'GET':
        return render_template('modern/product_form.html', product=None)
    
    try:
        data = request.get_json() if request.is_json else request.form
        
        name = data.get('name', '').strip()
        url = data.get('url', '').strip()
        
        if not name or not url:
            return jsonify({'success': False, 'error': 'Name and URL are required'}), 400
        
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Determine product type
        product_type = data.get('product_type', 'physical_product')  # 'physical_product' or 'cpa_offer'
        
        product_id = db.create_product(
            user_id=discord_id,
            name=name,
            url=url,
            product_type=product_type,
            image_url=data.get('image_url', ''),
            offer_url=data.get('offer_url', url) if product_type == 'cpa_offer' else '',
            price=float(data.get('price')) if data.get('price') else None,
            price_text=data.get('price_text', ''),
            description=data.get('description', ''),
            cpa_network=data.get('cpa_network', ''),
            cpa_offer_id=data.get('cpa_offer_id', ''),
            cpa_payout=float(data.get('cpa_payout')) if data.get('cpa_payout') else None,
            conversion_action=data.get('conversion_action', 'purchase'),  # 'purchase', 'signup', 'install'
            tracking_url=data.get('tracking_url', ''),
            category=data.get('category', '')
        )
        
        if product_id:
            return jsonify({
                'success': True,
                'product_id': product_id,
                'message': 'Product created successfully',
                'redirect': url_for('products.products_list')
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to create product'}), 500
            
    except Exception as e:
        print(f"Error creating product: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/<product_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    """Edit an existing product"""
    try:
        is_owner, product, _ = verify_product_ownership(product_id)
        
        if not product:
            flash('Product not found', 'error')
            return redirect(url_for('products.products_list'))
        
        if not is_owner:
            if request.method == 'GET':
                return jsonify({'success': False, 'error': 'Unauthorized'}), 403
            flash('Unauthorized access', 'error')
            return redirect(url_for('products.products_list'))
        
        if request.method == 'GET':
            # Return product as JSON for modal
            return jsonify({'success': True, 'product': product})
        
        # POST - update product
        data = request.get_json() if request.is_json else request.form
        
        updates = {
            'name': data.get('name', '').strip(),
            'url': data.get('url', '').strip(),
            'price': float(data.get('price')) if data.get('price') else None,
            'price_text': data.get('price_text', ''),
            'description': data.get('description', ''),
            'cpa_network': data.get('cpa_network', ''),
            'cpa_offer_id': data.get('cpa_offer_id', ''),
            'tracking_url': data.get('tracking_url', ''),
            'category': data.get('category', '')
        }
        
        success = db.update_product(product_id, updates)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Product updated successfully',
                'redirect': url_for('products.products_list')
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update product'}), 500
            
    except Exception as e:
        print(f"Error editing product: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/<product_id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete_product(product_id):
    """Delete a product"""
    try:
        is_owner, product, _ = verify_product_ownership(product_id)
        
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        success = db.delete_product(product_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Product deleted successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete product'}), 500
            
    except Exception as e:
        print(f"Error deleting product: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/api/list')
@login_required
def api_list_products():
    """API endpoint to get all user products as JSON"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        products = db.get_user_products(discord_id)
        
        return jsonify({
            'success': True,
            'products': products
        })
    except Exception as e:
        print(f"Error getting products: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@product_bp.route('/cpa-help')
@login_required
def cpa_help():
    """CPA Network setup help page"""
    return render_template('modern/cpa_network_help.html')

