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
import json

from tada.models import POC
from tada.serializers import (
    POCSerializer,
    POCListSerializer,
    POCCreateSerializer,
    POCUpdateSerializer
)


class POCListCreateView(APIView):
    """
    View to list all POCs or create a new one.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        List all POCs with optional filters.
        
        Query params:
        - region: Filter by region (costa/sierra/oriente/insular)
        - city: Search by city (contains)
        - id_poc: Search by POC ID (contains)
        - search: Search in name (contains)
        - page: Page number (default: 1)
        - page_size: Items per page (default: varies)
        """
        queryset = POC.objects.all()

        # Filter by region
        region = request.query_params.get('region')
        if region:
            queryset = queryset.filter(region=region)

        # Filter by city
        city = request.query_params.get('city')
        if city:
            queryset = queryset.filter(city__icontains=city)

        # Filter by id_poc
        id_poc = request.query_params.get('id_poc')
        if id_poc:
            queryset = queryset.filter(id_poc__icontains=id_poc)

        # Search by name
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        queryset = queryset.order_by('-created_at')
        
        # Apply pagination
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = POCListSerializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """
        Create a new POC.
        """
        serializer = POCCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class POCRetrieveUpdateDestroyView(APIView):
    """
    View to retrieve, update or delete a specific POC.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(POC, pk=pk)

    def get(self, request, pk):
        """
        Get a specific POC with its details.
        """
        poc = self.get_object(pk)
        serializer = POCSerializer(poc)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        Completely update a POC.
        """
        poc = self.get_object(pk)
        serializer = POCUpdateSerializer(poc, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(POCSerializer(poc).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Partially update a POC.
        """
        poc = self.get_object(pk)
        serializer = POCUpdateSerializer(poc, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(POCSerializer(poc).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Delete a POC.
        """
        poc = self.get_object(pk)
        poc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class POCBulkCreateFromExcelView(APIView):
    """
    View to create multiple POCs from an Excel file.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Create or update multiple POCs from an Excel file.

        The Excel file must have the following columns:
        - id_poc: Unique POC identifier (required)
        - city: City in Ecuador (required)
        - name: POC name (required)
        - region: Region - costa, sierra, oriente, or insular (required)
        - homologated_names: Comma-separated list of alternative names (optional)
        - active: true/false (optional, default: true)

        Behavior:
        - If id_poc does not exist: creates a new POC
        - If id_poc already exists: updates the existing POC
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
            required_columns = ['id_poc', 'city', 'name', 'region']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                return Response(
                    {'error': f'Missing columns in the file: {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            created_pocs = []
            errors = []

            for index, row in df.iterrows():
                try:
                    # Validate region
                    region_value = str(row['region']).lower().strip()
                    valid_regions = ['costa', 'sierra', 'oriente', 'insular']
                    if region_value not in valid_regions:
                        errors.append(f"Row {index+2}: Region must be one of: {', '.join(valid_regions)}")
                        continue

                    # Validate required fields
                    if pd.isna(row['id_poc']) or pd.isna(row['city']) or pd.isna(row['name']):
                        errors.append(f"Row {index+2}: Required fields are empty")
                        continue

                    # Process homologated_names
                    homologated_names = []
                    if 'homologated_names' in row and not pd.isna(row['homologated_names']):
                        # Split by comma and clean
                        names_str = str(row['homologated_names'])
                        homologated_names = [n.strip() for n in names_str.split(',') if n.strip()]

                    # Prepare data
                    poc_data = {
                        'id_poc': str(row['id_poc']).strip(),
                        'city': str(row['city']).strip(),
                        'name': str(row['name']).strip(),
                        'region': region_value,
                        'homologated_names': homologated_names
                    }

                    # Check if a POC with this id_poc already exists
                    existing_poc = POC.objects.filter(id_poc=poc_data['id_poc']).first()

                    if existing_poc:
                        # Update existing POC
                        serializer = POCUpdateSerializer(existing_poc, data=poc_data, partial=True)
                        if serializer.is_valid():
                            poc = serializer.save()
                            created_pocs.append({
                                'id_poc': poc.id_poc,
                                'name': poc.name,
                                'city': poc.city,
                                'region': poc.region,
                                'id': poc.id,
                                'action': 'updated',
                                'row': index + 2
                            })
                        else:
                            errors.append(f"Row {index+2}: Validation error - {serializer.errors}")
                    else:
                        # Create new POC
                        serializer = POCCreateSerializer(data=poc_data)
                        if serializer.is_valid():
                            poc = serializer.save()
                            created_pocs.append({
                                'id_poc': poc.id_poc,
                                'name': poc.name,
                                'city': poc.city,
                                'region': poc.region,
                                'id': poc.id,
                                'action': 'created',
                                'row': index + 2
                            })
                        else:
                            errors.append(f"Row {index+2}: Validation error - {serializer.errors}")

                except Exception as e:
                    errors.append(f"Row {index+2}: Unexpected error - {str(e)}")

            # Count the actions performed
            created_count = len([p for p in created_pocs if p.get('action') == 'created'])
            updated_count = len([p for p in created_pocs if p.get('action') == 'updated'])

            response_data = {
                'total_processed': len(created_pocs),
                'created': created_count,
                'updated': updated_count,
                'total_rows': len(df),
                'errors_count': len(errors),
                'results': created_pocs
            }

            if errors:
                response_data['errors'] = errors

            status_code = status.HTTP_201_CREATED if created_pocs else status.HTTP_400_BAD_REQUEST

            return Response(response_data, status=status_code)

        except Exception as e:
            return Response(
                {'error': f'Error processing Excel file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class POCDownloadTemplateView(APIView):
    """
    View to download an Excel template for bulk POC creation.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Download an Excel template with example data for bulk POC creation.
        """
        # Create sample data with examples
        sample_data = {
            'id_poc': [
                'POC001',
                'POC002',
                'POC003',
                'POC004',
                'POC005'
            ],
            'city': [
                'Quito',
                'Guayaquil',
                'Cuenca',
                'Tena',
                'Puerto Ayora'
            ],
            'name': [
                'Supermaxi Quito Norte',
                'Mi Comisariato Guayaquil',
                'Santa María Cuenca',
                'Tienda El Oriente',
                'Distribuidora Galápagos'
            ],
            'region': [
                'sierra',
                'costa',
                'sierra',
                'oriente',
                'insular'
            ],
            'homologated_names': [
                'Supermaxi Norte,Super Norte,Maxi Norte',
                'Mi Comisariato GYE,Comisariato Guayaquil',
                'Santa Maria,SM Cuenca',
                '',
                'Dist Galapagos,Distribuidora Islas'
            ],
            'active': [
                True,
                True,
                True,
                True,
                True
            ]
        }
        
        # Create DataFrame
        df = pd.DataFrame(sample_data)
        
        # Create a BytesIO buffer for the Excel file
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Write the main data sheet
            df.to_excel(writer, index=False, sheet_name='POC Template')
            
            # Create instructions sheet
            instructions_data = {
                'Column': [
                    'id_poc',
                    'city',
                    'name',
                    'region',
                    'homologated_names',
                    'active'
                ],
                'Required': [
                    'YES',
                    'YES',
                    'YES',
                    'YES',
                    'Optional',
                    'Optional (default: true)'
                ],
                'Description': [
                    'Unique POC identifier code',
                    'City name in Ecuador',
                    'POC name/description',
                    'Region: "costa", "sierra", "oriente", or "insular"',
                    'Comma-separated list of alternative names for matching (e.g., "Name1,Name2,Name3")',
                    'Whether the POC is active (true/false)'
                ],
                'Example': [
                    'POC001',
                    'Quito',
                    'Supermaxi Quito Norte',
                    'sierra',
                    'Supermaxi Norte,Super Norte,Maxi Norte',
                    'true'
                ]
            }
            
            instructions_df = pd.DataFrame(instructions_data)
            instructions_df.to_excel(writer, index=False, sheet_name='Instructions')
            
            # Create regions info sheet
            regions_data = {
                'Region': ['costa', 'sierra', 'oriente', 'insular'],
                'Description': [
                    'Coastal region',
                    'Mountain/Andean region',
                    'Eastern/Amazon region',
                    'Insular/Galápagos region'
                ],
                'Example Cities': [
                    'Guayaquil, Manta, Esmeraldas, Machala',
                    'Quito, Cuenca, Ambato, Riobamba, Ibarra',
                    'Tena, Puyo, Macas, Lago Agrio',
                    'Puerto Ayora, Puerto Baquerizo Moreno'
                ]
            }
            
            regions_df = pd.DataFrame(regions_data)
            regions_df.to_excel(writer, index=False, sheet_name='Regions Info')
        
        output.seek(0)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'poc_template_{timestamp}.xlsx'
        
        # Create HTTP response with Excel file
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
