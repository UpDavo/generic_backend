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

from tada.models import VentasProductosCompra
from tada.serializers import (
    VentasProductosCompraSerializer,
    VentasProductosCompraListSerializer,
    VentasProductosCompraCreateSerializer,
    VentasProductosCompraUpdateSerializer,
    VentasProductosCompraSimpleSerializer
)


class VentasProductosCompraListCreateView(APIView):
    """
    View to list all VentasProductosCompra or create a new one.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        List all VentasProductosCompra with optional filters.
        
        Query params:
        - code: Search by code (contains)
        - name: Search by name (contains)
        - brand: Filter by brand (contains)
        - category: Filter by category (contains)
        - origen: Filter by origen (importado/nacional)
        - returnable: Filter by returnable (true/false)
        - search: Search in name and code (contains)
        - page: Page number (default: 1)
        - page_size: Items per page (default: varies)
        """
        queryset = VentasProductosCompra.objects.all()

        # Filter by code
        code = request.query_params.get('code')
        if code:
            queryset = queryset.filter(code__icontains=code)

        # Filter by name
        name = request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)

        # Filter by brand
        brand = request.query_params.get('brand')
        if brand:
            queryset = queryset.filter(brand__icontains=brand)

        # Filter by category
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__icontains=category)

        # Filter by origen
        origen = request.query_params.get('origen')
        if origen:
            queryset = queryset.filter(origen=origen)

        # Filter by returnable
        returnable = request.query_params.get('returnable')
        if returnable:
            returnable_bool = returnable.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(returnable=returnable_bool)

        # Search by name or code
        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(code__icontains=search) |
                Q(homologated_names__icontains=search)
            )

        queryset = queryset.order_by('-created_at')
        
        # Apply pagination
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = VentasProductosCompraListSerializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """
        Create a new VentasProductosCompra.
        """
        serializer = VentasProductosCompraCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VentasProductosCompraSearchView(APIView):
    """
    View to search VentasProductosCompra without pagination.
    Returns products for quick search/autocomplete.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Search VentasProductosCompra by name or code.
        
        Query params:
        - search: Search term for name, code, or brand
        
        Returns:
            List of products matching the search criteria (no pagination)
        """
        search_term = request.query_params.get('search', '').strip()
        
        queryset = VentasProductosCompra.objects.all()
        
        # Apply search filter if provided
        if search_term:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(code__icontains=search_term) |
                Q(brand__icontains=search_term) |
                Q(homologated_names__icontains=search_term)
            )
        
        # Order by name and limit results
        queryset = queryset.order_by('name')[:100]
        
        serializer = VentasProductosCompraSimpleSerializer(queryset, many=True)
        return Response(serializer.data)


class VentasProductosCompraRetrieveUpdateDestroyView(APIView):
    """
    View to retrieve, update or delete a specific VentasProductosCompra.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(VentasProductosCompra, pk=pk)

    def get(self, request, pk):
        """
        Get a specific VentasProductosCompra.
        """
        producto = self.get_object(pk)
        serializer = VentasProductosCompraSerializer(producto)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        Completely update a VentasProductosCompra.
        """
        producto = self.get_object(pk)
        serializer = VentasProductosCompraUpdateSerializer(producto, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(VentasProductosCompraSerializer(producto).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Partially update a VentasProductosCompra.
        """
        producto = self.get_object(pk)
        serializer = VentasProductosCompraUpdateSerializer(producto, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(VentasProductosCompraSerializer(producto).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Delete a VentasProductosCompra.
        """
        producto = self.get_object(pk)
        producto.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VentasProductosCompraBulkCreateFromExcelView(APIView):
    """
    View to create multiple VentasProductosCompra from an Excel file.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create or update multiple VentasProductosCompra from an Excel file.

        The Excel file must have the following columns:
        - code: Unique product code (required)
        - name: Product name (required)
        - homologated_names: Comma-separated list of alternative names (optional)
        - mililiters_per_unit: Milliliters per unit (optional)
        - box_units: Units per box (optional)
        - primary_can: Primary can type (optional)
        - returnable: true/false (optional, default: false)
        - origen: importado/nacional (optional)
        - cost_per_unit: Cost per unit (optional)
        - cost_per_box: Cost per box (optional)
        - cost_per_hectoliter: Cost per hectoliter (optional)
        - brand: Product brand (optional)
        - category: Product category (optional)
        - hectoliter_per_unit: Hectoliters per unit (optional)
        - hectoliter_box: Hectoliters per box (optional)

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
            required_columns = ['code', 'name']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                return Response(
                    {'error': f'Missing columns in the file: {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            created_products = []
            errors = []

            print(f"\n🔄 Processing {len(df)} products...")
            for index, row in tqdm(df.iterrows(), total=len(df), desc="Creating/Updating Products", unit="row"):
                try:
                    # Validate required fields
                    if pd.isna(row['code']) or pd.isna(row['name']):
                        error_msg = f"Row {index+2}: Required fields are empty"
                        print(f"❌ {error_msg}")
                        errors.append(error_msg)
                        continue

                    # Process homologated_names
                    homologated_names = []
                    if 'homologated_names' in row and not pd.isna(row['homologated_names']):
                        names_str = str(row['homologated_names'])
                        homologated_names = [n.strip() for n in names_str.split(',') if n.strip()]

                    # Process returnable
                    returnable = False
                    if 'returnable' in row and not pd.isna(row['returnable']):
                        returnable_str = str(row['returnable']).lower()
                        returnable = returnable_str in ['true', '1', 'yes', 'sí', 'si']

                    # Prepare data
                    product_data = {
                        'code': str(row['code']).strip(),
                        'name': str(row['name']).strip(),
                        'homologated_names': homologated_names,
                        'mililiters_per_unit': float(row.get('mililiters_per_unit')) if not pd.isna(row.get('mililiters_per_unit')) else None,
                        'box_units': int(row.get('box_units')) if not pd.isna(row.get('box_units')) else None,
                        'primary_can': str(row.get('primary_can')).strip() if not pd.isna(row.get('primary_can')) else None,
                        'returnable': returnable,
                        'origen': str(row.get('origen')).strip() if not pd.isna(row.get('origen')) else None,
                        'cost_per_unit': float(row.get('cost_per_unit')) if not pd.isna(row.get('cost_per_unit')) else None,
                        'cost_per_box': float(row.get('cost_per_box')) if not pd.isna(row.get('cost_per_box')) else None,
                        'cost_per_hectoliter': float(row.get('cost_per_hectoliter')) if not pd.isna(row.get('cost_per_hectoliter')) else None,
                        'brand': str(row.get('brand')).strip() if not pd.isna(row.get('brand')) else None,
                        'category': str(row.get('category')).strip() if not pd.isna(row.get('category')) else None,
                        'hectoliter_per_unit': float(row.get('hectoliter_per_unit')) if not pd.isna(row.get('hectoliter_per_unit')) else None,
                        'hectoliter_box': float(row.get('hectoliter_box')) if not pd.isna(row.get('hectoliter_box')) else None,
                    }

                    # Check if a product with this code already exists
                    existing_product = VentasProductosCompra.objects.filter(code=product_data['code']).first()

                    if existing_product:
                        # Update existing product
                        serializer = VentasProductosCompraUpdateSerializer(existing_product, data=product_data, partial=True)
                        if serializer.is_valid():
                            producto = serializer.save()
                            created_products.append({
                                'code': producto.code,
                                'name': producto.name,
                                'id': producto.id,
                                'action': 'updated',
                                'row': index + 2
                            })
                        else:
                            error_msg = f"Row {index+2}: Validation error - {serializer.errors}"
                            print(f"❌ {error_msg}")
                            errors.append(error_msg)
                    else:
                        # Create new product
                        serializer = VentasProductosCompraCreateSerializer(data=product_data)
                        if serializer.is_valid():
                            producto = serializer.save()
                            created_products.append({
                                'code': producto.code,
                                'name': producto.name,
                                'id': producto.id,
                                'action': 'created',
                                'row': index + 2
                            })
                        else:
                            error_msg = f"Row {index+2}: Validation error - {serializer.errors}"
                            print(f"❌ {error_msg}")
                            errors.append(error_msg)

                except Exception as e:
                    error_msg = f"Row {index+2}: Error processing row - {str(e)}"
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


class VentasProductosCompraDownloadTemplateView(APIView):
    """
    View to download an Excel template for bulk creation of VentasProductosCompra.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Download an Excel template with the required columns for bulk creation.
        """
        # Create a sample DataFrame with the required columns
        data = {
            'code': ['PROD001', 'PROD002'],
            'name': ['Product 1', 'Product 2'],
            'homologated_names': ['Alt Name 1, Alt Name 2', 'Alt Name 3'],
            'mililiters_per_unit': [355, 500],
            'box_units': [24, 12],
            'primary_can': ['Aluminum', 'Glass'],
            'returnable': [True, False],
            'origen': ['nacional', 'importado'],
            'cost_per_unit': [12.50, 25.00],
            'cost_per_box': [300.00, 300.00],
            'cost_per_hectoliter': [3521.13, 5000.00],
            'brand': ['Brand A', 'Brand B'],
            'category': ['Beer', 'Wine'],
            'hectoliter_per_unit': [0.00355, 0.005],
            'hectoliter_box': [0.0852, 0.06]
        }

        df = pd.DataFrame(data)

        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='VentasProductosCompra')

        output.seek(0)

        # Create HTTP response
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="ventas_productos_compra_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'

        return response
