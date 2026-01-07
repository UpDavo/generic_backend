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

from tada.models import SKU
from tada.serializers import (
    SKUSerializer,
    SKUListSerializer,
    SKUCreateSerializer,
    SKUUpdateSerializer,
    SKUSimpleSerializer
)


class SKUListCreateView(APIView):
    """
    View to list all SKUs or create a new one.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        List all SKUs with optional filters.
        
        Query params:
        - type: Filter by type (principal/combo)
        - vendor_code: Search by vendor code (contains)
        - sku_vtex: Search by SKU VTEX (contains)
        - search: Search in name (contains)
        - page: Page number (default: 1)
        - page_size: Items per page (default: varies)
        """
        queryset = SKU.objects.all()

        # Filter by type
        sku_type = request.query_params.get('type')
        if sku_type:
            queryset = queryset.filter(type=sku_type)

        # Filter by vendor code
        vendor_code = request.query_params.get('vendor_code')
        if vendor_code:
            queryset = queryset.filter(vendor_code__icontains=vendor_code)

        # Filter by sku_vtex
        sku_vtex = request.query_params.get('sku_vtex')
        if sku_vtex:
            queryset = queryset.filter(sku_vtex__icontains=sku_vtex)

        # Search by name
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        queryset = queryset.order_by('-created_at')
        
        # Apply pagination
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = SKUListSerializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """
        Create a new SKU.
        """
        serializer = SKUCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SKUPrincipalSearchView(APIView):
    """
    View to search principal SKUs without pagination.
    Returns only principal type SKUs for quick search/autocomplete.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Search principal SKUs by name.
        
        Query params:
        - search: Search term for name, sku_vtex, or vendor_code
        
        Returns:
            List of principal SKUs matching the search criteria (no pagination)
        """
        search_term = request.query_params.get('search', '').strip()
        
        # Start with principal SKUs only
        queryset = SKU.objects.filter(type='principal')
        
        # Apply search filter if provided
        if search_term:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(sku_vtex__icontains=search_term) |
                Q(vendor_code__icontains=search_term) |
                Q(homologated_names__icontains=search_term)
            )
        
        # Order by name and limit results
        queryset = queryset.order_by('name')[:100]
        
        serializer = SKUSimpleSerializer(queryset, many=True)
        return Response(serializer.data)


class SKURetrieveUpdateDestroyView(APIView):
    """
    View to retrieve, update or delete a specific SKU.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(SKU, pk=pk)

    def get(self, request, pk):
        """
        Get a specific SKU with its relationships.
        """
        sku = self.get_object(pk)
        serializer = SKUSerializer(sku)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        Completely update a SKU.
        """
        sku = self.get_object(pk)
        serializer = SKUUpdateSerializer(sku, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(SKUSerializer(sku).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Partially update a SKU.
        """
        sku = self.get_object(pk)
        serializer = SKUUpdateSerializer(sku, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(SKUSerializer(sku).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Delete a SKU.
        """
        sku = self.get_object(pk)
        sku.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SKUBulkCreateFromExcelView(APIView):
    """
    View to create multiple SKUs from an Excel file.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create or update multiple SKUs from an Excel file.

        The Excel file must have the following columns:
        - type: 'principal' or 'combo'
        - vendor_code: Vendor code
        - sku_vtex: SKU in VTEX (unique)
        - name: Product name
        - units: Number of units (optional, default: 1)
        - milliliters_per_unit: Milliliters per unit (optional)
        - units_per_box: Units per box (optional)
        - hectoliters_per_unit: Hectoliters per unit (optional)
        - hectoliters_per_box: Hectoliters per box (optional)
        - homologated_names: Comma-separated list of alternative names (optional)
        - active: true/false (optional, default: true)
        - child_skus_vtex: Child SKUs separated by commas (only for combos, optional)

        Behavior:
        - If sku_vtex does not exist: creates a new SKU
        - If sku_vtex already exists: updates the existing SKU
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
            required_columns = ['type', 'vendor_code', 'sku_vtex', 'name']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                return Response(
                    {'error': f'Missing columns in the file: {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            created_skus = []
            errors = []

            # First pass: Create/update SKUs without child relationships
            print(f"\n🔄 Processing {len(df)} SKUs...")
            for index, row in tqdm(df.iterrows(), total=len(df), desc="Creating/Updating SKUs", unit="row"):
                try:
                    # Validate type
                    type_value = str(row['type']).lower().strip()
                    
                    if type_value not in ['principal', 'combo']:
                        error_msg = f"Row {index+2}: Type must be 'principal' or 'combo'"
                        print(f"❌ {error_msg}")
                        errors.append(error_msg)
                        continue

                    # Validate required fields
                    if pd.isna(row['vendor_code']) or pd.isna(row['sku_vtex']) or pd.isna(row['name']):
                        error_msg = f"Row {index+2}: Required fields are empty"
                        print(f"❌ {error_msg}")
                        errors.append(error_msg)
                        continue

                    # Process homologated_names
                    homologated_names = []
                    if 'homologated_names' in row and not pd.isna(row['homologated_names']):
                        # Split by comma and clean
                        names_str = str(row['homologated_names'])
                        homologated_names = [n.strip() for n in names_str.split(',') if n.strip()]

                    # Prepare data
                    sku_data = {
                        'type': type_value,
                        'vendor_code': str(row['vendor_code']).strip(),
                        'sku_vtex': str(row['sku_vtex']).strip(),
                        'name': str(row['name']).strip(),
                        'units': int(row.get('units', 1)) if not pd.isna(row.get('units')) else 1,
                        'milliliters_per_unit': float(row.get('milliliters_per_unit')) if not pd.isna(row.get('milliliters_per_unit')) else None,
                        'units_per_box': int(row.get('units_per_box')) if not pd.isna(row.get('units_per_box')) else None,
                        'hectoliters_per_unit': float(row.get('hectoliters_per_unit')) if not pd.isna(row.get('hectoliters_per_unit')) else None,
                        'hectoliters_per_box': float(row.get('hectoliters_per_box')) if not pd.isna(row.get('hectoliters_per_box')) else None,
                        'homologated_names': homologated_names
                    }

                    # Check if a SKU with this sku_vtex already exists
                    existing_sku = SKU.objects.filter(sku_vtex=sku_data['sku_vtex']).first()

                    if existing_sku:
                        # Update existing SKU (without relationships for now)
                        serializer = SKUUpdateSerializer(existing_sku, data=sku_data, partial=True)
                        if serializer.is_valid():
                            sku = serializer.save()
                            created_skus.append({
                                'sku_vtex': sku.sku_vtex,
                                'name': sku.name,
                                'type': sku.type,
                                'id': sku.id,
                                'action': 'updated',
                                'row': index + 2
                            })
                        else:
                            error_msg = f"Row {index+2}: Validation error - {serializer.errors}"
                            print(f"❌ {error_msg}")
                            errors.append(error_msg)
                    else:
                        # Create new SKU (without relationships for now)
                        serializer = SKUCreateSerializer(data=sku_data)
                        if serializer.is_valid():
                            sku = serializer.save()
                            created_skus.append({
                                'sku_vtex': sku.sku_vtex,
                                'name': sku.name,
                                'type': sku.type,
                                'id': sku.id,
                                'action': 'created',
                                'row': index + 2
                            })
                        else:
                            error_msg = f"Row {index+2}: Validation error - {serializer.errors}"
                            print(f"❌ {error_msg}")
                            errors.append(error_msg)

                except Exception as e:
                    error_msg = f"Row {index+2}: Unexpected error - {str(e)}"
                    print(f"❌ {error_msg}")
                    errors.append(error_msg)

            # Second pass: Assign child SKU relationships (only for combos)
            combo_rows = df[df['type'].str.lower().str.strip() == 'combo']
            if 'child_skus_vtex' in df.columns and len(combo_rows) > 0:
                print(f"\n🔗 Assigning child relationships to combos...")
                for index, row in tqdm(combo_rows.iterrows(), total=len(combo_rows), desc="Assigning children", unit="combo"):
                    try:
                        sku_vtex = str(row['sku_vtex']).strip()
                        child_skus_vtex = row.get('child_skus_vtex')

                        # Only process if has children defined
                        if not pd.isna(child_skus_vtex):
                            sku = SKU.objects.filter(sku_vtex=sku_vtex).first()
                            if sku:
                                # Parse child SKUs (comma separated)
                                children_vtex_list = [s.strip() for s in str(child_skus_vtex).split(',')]
                                
                                # Find child SKUs
                                children = SKU.objects.filter(sku_vtex__in=children_vtex_list)
                                
                                if children.exists():
                                    # Assign children to combo
                                    sku.child_skus.set(children)
                                    
                                    # Update the record in created_skus
                                    for item in created_skus:
                                        if item['sku_vtex'] == sku_vtex:
                                            item['children_assigned'] = children.count()
                                            break
                                else:
                                    error_msg = f"Row {index+2}: No child SKUs found with the specified codes"
                                    print(f"❌ {error_msg}")
                                    errors.append(error_msg)

                    except Exception as e:
                        error_msg = f"Row {index+2}: Error assigning children - {str(e)}"
                        print(f"❌ {error_msg}")
                        errors.append(error_msg)

            # Count the actions performed
            created_count = len([s for s in created_skus if s.get('action') == 'created'])
            updated_count = len([s for s in created_skus if s.get('action') == 'updated'])

            print(f"\n✅ Summary: Created {created_count}, Updated {updated_count}, Errors {len(errors)}")

            response_data = {
                'total_processed': len(created_skus),
                'created': created_count,
                'updated': updated_count,
                'total_rows': len(df),
                'errors_count': len(errors),
                'results': created_skus
            }

            if errors:
                response_data['errors'] = errors

            status_code = status.HTTP_201_CREATED if created_skus else status.HTTP_400_BAD_REQUEST

            return Response(response_data, status=status_code)

        except Exception as e:
            print(f"\n❌ FATAL ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Error processing Excel file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class SKUDownloadTemplateView(APIView):
    """
    View to download an Excel template for bulk SKU creation.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Download an Excel template with example data for bulk SKU creation.
        
        The template includes:
        - All required and optional columns
        - Example rows showing how to create principal SKUs
        - Example rows showing how to create combo SKUs with children
        - Instructions on how to use child_skus_vtex for combos
        
        Returns:
            Excel file with template and examples
        """
        # Create sample data with examples
        sample_data = {
            'type': [
                'principal',
                'principal',
                'principal',
                'combo',
                'combo'
            ],
            'vendor_code': [
                'V001',
                'V001',
                'V002',
                'V003',
                'V003'
            ],
            'sku_vtex': [
                'SKU001',
                'SKU002',
                'SKU003',
                'COMBO001',
                'COMBO002'
            ],
            'name': [
                'Beer 355ml',
                'Chips 150g',
                'Soda 500ml',
                'Beer + Chips Combo',
                'Complete Pack (Beer + Chips + Soda)'
            ],
            'units': [
                1,
                1,
                1,
                2,
                3
            ],
            'milliliters_per_unit': [
                355.0,
                None,
                500.0,
                355.0,
                1210.0
            ],
            'units_per_box': [
                24,
                50,
                12,
                12,
                6
            ],
            'hectoliters_per_unit': [
                0.00355,
                None,
                0.005,
                0.00355,
                0.0121
            ],
            'hectoliters_per_box': [
                0.0852,
                None,
                0.06,
                0.0426,
                0.0726
            ],
            'active': [
                True,
                True,
                True,
                True,
                True
            ],
            'homologated_names': [
                'Cerveza 355ml,Beer 355,Cerveza',
                'Chifles,Papas Fritas,Snacks',
                'Gaseosa 500ml,Soda 500,Refresco',
                '',
                ''
            ],
            'child_skus_vtex': [
                '',
                '',
                '',
                'SKU001,SKU002',
                'SKU001,SKU002,SKU003'
            ]
        }
        
        # Create DataFrame
        df = pd.DataFrame(sample_data)
        
        # Create a BytesIO buffer for the Excel file
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Write the main data sheet
            df.to_excel(writer, index=False, sheet_name='SKU Template')
            
            # Create instructions sheet
            instructions_data = {
                'Column': [
                    'type',
                    'vendor_code',
                    'sku_vtex',
                    'name',
                    'units',
                    'milliliters_per_unit',
                    'units_per_box',
                    'hectoliters_per_unit',
                    'hectoliters_per_box',
                    'homologated_names',
                    'active',
                    'child_skus_vtex'
                ],
                'Required': [
                    'YES',
                    'YES',
                    'YES',
                    'YES',
                    'Optional (default: 1)',
                    'Optional',
                    'Optional',
                    'Optional',
                    'Optional',
                    'Optional',
                    'Optional (default: true)',
                    'Optional (only for combos)'
                ],
                'Description': [
                    'Type of SKU: "principal" for individual products, "combo" for product bundles',
                    'Vendor identification code',
                    'Unique SKU code in VTEX system',
                    'Product name/description',
                    'Number of units in the SKU',
                    'Milliliters per unit (for liquid products)',
                    'Number of units per box',
                    'Hectoliters per unit (for liquid products)',
                    'Hectoliters per box (for liquid products)',
                    'Comma-separated list of alternative names for matching (e.g., "Alt Name 1,Alt Name 2")',
                    'Whether the SKU is active (true/false)',
                    'For combos only: comma-separated list of child SKU codes (e.g., "SKU001,SKU002"). Leave empty for principal SKUs.'
                ],
                'Example': [
                    'principal',
                    'V001',
                    'SKU001',
                    'Beer 355ml',
                    '1',
                    '355.0',
                    '24',
                    '0.00355',
                    '0.0852',
                    'Cerveza 355ml,Beer 355,Cerveza',
                    'true',
                    'SKU001,SKU002'
                ]
            }
            
            instructions_df = pd.DataFrame(instructions_data)
            instructions_df.to_excel(writer, index=False, sheet_name='Instructions')
            
            # Create workflow sheet
            workflow_data = {
                'Step': [
                    '1',
                    '2',
                    '3',
                    '4',
                    '5',
                    '6'
                ],
                'Action': [
                    'Create Principal SKUs First',
                    'Fill Required Columns',
                    'Add Optional Data',
                    'Create Combo SKUs',
                    'Upload File',
                    'Review Results'
                ],
                'Details': [
                    'Start by creating all principal (individual) SKUs. These will be the building blocks for combos.',
                    'Make sure to fill type, vendor_code, sku_vtex, and name for all SKUs.',
                    'Add measurements (milliliters, hectoliters, units) and other optional fields as needed.',
                    'For combo SKUs, set type="combo" and list child SKU codes in child_skus_vtex column, separated by commas (e.g., "SKU001,SKU002").',
                    'Upload the completed Excel file to the /skus/bulk-create-excel/ endpoint.',
                    'Check the response for created/updated counts and any errors.'
                ]
            }
            
            workflow_df = pd.DataFrame(workflow_data)
            workflow_df.to_excel(writer, index=False, sheet_name='Workflow')
        
        output.seek(0)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'sku_template_{timestamp}.xlsx'
        
        # Create HTTP response with Excel file
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response

