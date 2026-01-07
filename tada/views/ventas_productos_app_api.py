from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
import pandas as pd
from io import BytesIO
from datetime import datetime
from tqdm import tqdm

from tada.models import VentasProductosApp, VentasProductosCompra, VentasProductosAppMaterial
from tada.serializers import (
    VentasProductosAppSerializer,
    VentasProductosAppListSerializer,
    VentasProductosAppCreateSerializer,
    VentasProductosAppUpdateSerializer,
    VentasProductosAppSimpleSerializer
)


class VentasProductosAppListCreateView(APIView):
    """
    View to list all VentasProductosApp or create a new one.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        List all VentasProductosApp with optional filters.
        
        Query params:
        - type: Filter by type (principal/combo)
        - code: Search by code (contains)
        - name: Search by name (contains)
        - search: Search in name and code (contains)
        - page: Page number (default: 1)
        - page_size: Items per page (default: varies)
        """
        queryset = VentasProductosApp.objects.all()

        # Filter by type
        product_type = request.query_params.get('type')
        if product_type:
            queryset = queryset.filter(type=product_type)

        # Filter by code
        code = request.query_params.get('code')
        if code:
            queryset = queryset.filter(code__icontains=code)

        # Filter by name
        name = request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)

        # Search by name or code
        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(code__icontains=search)
            )

        queryset = queryset.order_by('-created_at')
        
        # Apply pagination
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = VentasProductosAppListSerializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """
        Create a new VentasProductosApp.
        """
        serializer = VentasProductosAppCreateSerializer(data=request.data)
        if serializer.is_valid():
            producto = serializer.save()
            return Response(VentasProductosAppSerializer(producto).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VentasProductosAppPrincipalSearchView(APIView):
    """
    View to search principal VentasProductosApp without pagination.
    Returns only principal type products for quick search/autocomplete.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Search principal VentasProductosApp by name or code.
        
        Query params:
        - search: Search term for name or code
        
        Returns:
            List of principal products matching the search criteria (no pagination)
        """
        search_term = request.query_params.get('search', '').strip()
        
        # Start with principal products only
        queryset = VentasProductosApp.objects.filter(type='principal')
        
        # Apply search filter if provided
        if search_term:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(code__icontains=search_term)
            )
        
        # Order by name and limit results
        queryset = queryset.order_by('name')[:100]
        
        serializer = VentasProductosAppSimpleSerializer(queryset, many=True)
        return Response(serializer.data)


class VentasProductosAppRetrieveUpdateDestroyView(APIView):
    """
    View to retrieve, update or delete a specific VentasProductosApp.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(VentasProductosApp, pk=pk)

    def get(self, request, pk):
        """
        Get a specific VentasProductosApp with its materials.
        """
        producto = self.get_object(pk)
        serializer = VentasProductosAppSerializer(producto)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        Completely update a VentasProductosApp.
        """
        producto = self.get_object(pk)
        serializer = VentasProductosAppUpdateSerializer(producto, data=request.data)
        if serializer.is_valid():
            producto = serializer.save()
            return Response(VentasProductosAppSerializer(producto).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Partially update a VentasProductosApp.
        """
        producto = self.get_object(pk)
        serializer = VentasProductosAppUpdateSerializer(producto, data=request.data, partial=True)
        if serializer.is_valid():
            producto = serializer.save()
            return Response(VentasProductosAppSerializer(producto).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Delete a VentasProductosApp.
        """
        producto = self.get_object(pk)
        producto.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VentasProductosAppBulkCreateFromExcelView(APIView):
    """
    View to create multiple VentasProductosApp from an Excel file.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create or update multiple VentasProductosApp from an Excel file.

        The Excel file must have the following columns:
        - type: 'principal' or 'combo' (required)
        - code: Unique product code (required)
        - name: Product name (required)
        - unit: Quantity/units (optional, default: 1)
        - materials: Comma-separated list of material codes with quantities in format "CODE:QTY,CODE:QTY" (optional, for combos)

        Example for materials column: "PROD001:2.5,PROD002:1.0"

        Behavior:
        - If code does not exist: creates a new product
        - If code already exists: updates the existing product
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'An Excel file is required in the "file" field'},
                status=status.HTTP_400_BAD_REQUEST
            )

        excel_file = request.FILES['file']

        # Validate that it's an Excel file
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            return Response(
                {'error': 'The file must be an Excel file (.xlsx or .xls)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Read the Excel file
            df = pd.read_excel(BytesIO(excel_file.read()))

            # Validate that required columns exist
            required_columns = ['type', 'code', 'name']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                return Response(
                    {'error': f'Missing columns in the file: {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            created_products = []
            errors = []

            # First pass: Create/update products without materials
            print(f"\n🔄 Processing {len(df)} products...")
            for index, row in tqdm(df.iterrows(), total=len(df), desc="Creating/Updating Products", unit="row"):
                try:
                    # Validate type
                    type_value = str(row['type']).lower().strip()
                    
                    if type_value not in ['principal', 'combo']:
                        error_msg = f"Row {index+2}: Type must be 'principal' or 'combo'"
                        print(f"❌ {error_msg}")
                        errors.append(error_msg)
                        continue

                    # Validate required fields
                    if pd.isna(row['code']) or pd.isna(row['name']):
                        error_msg = f"Row {index+2}: Required fields are empty"
                        print(f"❌ {error_msg}")
                        errors.append(error_msg)
                        continue

                    # Prepare data
                    product_data = {
                        'type': type_value,
                        'code': str(row['code']).strip(),
                        'name': str(row['name']).strip(),
                        'unit': int(row.get('unit', 1)) if not pd.isna(row.get('unit')) else 1,
                    }

                    # Check if a product with this code already exists
                    existing_product = VentasProductosApp.objects.filter(code=product_data['code']).first()

                    if existing_product:
                        # Update existing product (without materials for now)
                        for key, value in product_data.items():
                            setattr(existing_product, key, value)
                        existing_product.save()
                        producto = existing_product
                        action = 'updated'
                    else:
                        # Create new product (without materials for now)
                        producto = VentasProductosApp.objects.create(**product_data)
                        action = 'created'

                    created_products.append({
                        'code': producto.code,
                        'name': producto.name,
                        'type': producto.type,
                        'id': producto.id,
                        'action': action,
                        'row': index + 2
                    })

                except Exception as e:
                    error_msg = f"Row {index+2}: Error processing row - {str(e)}"
                    print(f"❌ {error_msg}")
                    errors.append(error_msg)
                    continue

            # Second pass: Add materials to combos
            print(f"\n🔄 Processing materials for combos...")
            for index, row in tqdm(df.iterrows(), total=len(df), desc="Adding Materials", unit="row"):
                try:
                    if pd.isna(row['code']):
                        continue

                    code = str(row['code']).strip()
                    producto = VentasProductosApp.objects.filter(code=code).first()

                    if not producto:
                        continue

                    # Process materials if present
                    if 'materials' in row and not pd.isna(row['materials']):
                        materials_str = str(row['materials'])
                        
                        # Clear existing materials
                        producto.material_items.all().delete()
                        
                        # Parse materials: "CODE:QTY,CODE:QTY"
                        material_pairs = [m.strip() for m in materials_str.split(',') if m.strip()]
                        
                        for pair in material_pairs:
                            if ':' not in pair:
                                error_msg = f"Row {index+2}: Invalid material format '{pair}'. Expected 'CODE:QTY'"
                                print(f"⚠️ {error_msg}")
                                errors.append(error_msg)
                                continue
                            
                            material_code, quantity_str = pair.split(':', 1)
                            material_code = material_code.strip()
                            
                            try:
                                quantity = float(quantity_str.strip())
                            except ValueError:
                                error_msg = f"Row {index+2}: Invalid quantity '{quantity_str}' for material '{material_code}'"
                                print(f"⚠️ {error_msg}")
                                errors.append(error_msg)
                                continue
                            
                            # Find material by code
                            material = VentasProductosCompra.objects.filter(code=material_code).first()
                            
                            if not material:
                                error_msg = f"Row {index+2}: Material with code '{material_code}' not found"
                                print(f"⚠️ {error_msg}")
                                errors.append(error_msg)
                                continue
                            
                            # Create material relationship
                            VentasProductosAppMaterial.objects.create(
                                ventas_productos_app=producto,
                                ventas_productos_compra=material,
                                quantity=quantity
                            )

                except Exception as e:
                    error_msg = f"Row {index+2}: Error processing materials - {str(e)}"
                    print(f"❌ {error_msg}")
                    errors.append(error_msg)
                    continue

            return Response({
                'message': f'Process completed. {len(created_products)} products processed.',
                'created_count': len([p for p in created_products if p['action'] == 'created']),
                'updated_count': len([p for p in created_products if p['action'] == 'updated']),
                'products': created_products,
                'errors_count': len(errors),
                'errors': errors
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': f'Error processing Excel file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class VentasProductosAppDownloadTemplateView(APIView):
    """
    View to download an Excel template for bulk creation of VentasProductosApp.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Download an Excel template with the required columns for bulk creation.
        """
        # Create a sample DataFrame with the required columns
        data = {
            'type': ['principal', 'combo'],
            'code': ['APP001', 'APP002'],
            'name': ['App Product 1', 'Combo Product 2'],
            'unit': [1, 2],
            'materials': ['', 'PROD001:2.5,PROD002:1.0']
        }

        df = pd.DataFrame(data)

        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='VentasProductosApp')

        output.seek(0)

        # Create HTTP response
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="ventas_productos_app_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'

        return response
