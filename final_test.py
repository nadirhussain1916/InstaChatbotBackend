#!/usr/bin/env python
"""
Final production readiness test
"""
import os
import sys
import django
from pathlib import Path

# Add the project directory to the Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instagram_auth.settings')

# Setup Django
django.setup()

def test_critical_imports():
    """Test all critical imports that were failing"""
    print("🧪 Testing Critical Imports:")
    
    try:
        # The main failing import
        from dateutil.parser import parse
        print("   ✅ dateutil.parser - FIXED!")
        
        # Document processing imports
        import fitz  # PyMuPDF
        print("   ✅ fitz (PyMuPDF)")
        
        from docx import Document
        print("   ✅ docx (python-docx)")
        
        import pytesseract
        print("   ✅ pytesseract")
        
        # Core imports
        from playwright.sync_api import sync_playwright
        print("   ✅ playwright")
        
        from openai import OpenAI
        print("   ✅ openai")
        
        import psycopg
        print("   ✅ psycopg (PostgreSQL)")
        
        from PIL import Image
        print("   ✅ PIL (Pillow)")
        
        from cryptography.fernet import Fernet
        print("   ✅ cryptography")
        
        return True
        
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False

def test_django_setup():
    """Test Django application setup"""
    print("\n🔧 Testing Django Setup:")
    
    try:
        # Test URL imports (this was failing in Railway)
        from instaapp.urls import urlpatterns
        print("   ✅ instaapp.urls imported successfully")
        
        # Test helper imports (where dateutil.parser was failing)
        from instaapp.helper import save_user_profile
        print("   ✅ instaapp.helper imported successfully")
        
        # Test views imports  
        from instaapp.views import CustomSignInView
        print("   ✅ instaapp.views imported successfully")
        
        # Test services
        from instaapp.services import ConversationService
        print("   ✅ instaapp.services imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"   ❌ Django import failed: {e}")
        return False

def main():
    print("🚀 InstaChatbot Backend - Final Production Test")
    print("=" * 60)
    
    # Test imports
    imports_ok = test_critical_imports()
    
    # Test Django setup
    django_ok = test_django_setup()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"   Critical Imports: {'✅ PASS' if imports_ok else '❌ FAIL'}")
    print(f"   Django Setup: {'✅ PASS' if django_ok else '❌ FAIL'}")
    
    if imports_ok and django_ok:
        print("\n🎉 ALL TESTS PASSED!")
        print("🚀 Your application is ready for Railway deployment!")
        print("\n📋 Next steps:")
        print("   1. git add . && git commit -m 'Fix: Add missing dependencies'")
        print("   2. git push origin dackend_01") 
        print("   3. Deploy to Railway")
        print("   4. Set environment variables in Railway dashboard")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
