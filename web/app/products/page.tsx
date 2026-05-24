import { prisma } from '@/lib/prisma'
import { ProductCard } from '@/components/ProductCard'

export const revalidate = 60

interface SearchParams {
  category?: string
  search?: string
}

async function getProducts(params: SearchParams) {
  const where: any = {}
  
  if (params.category) {
    where.category = params.category
  }
  
  if (params.search) {
    where.OR = [
      { name: { contains: params.search, mode: 'insensitive' } },
      { description: { contains: params.search, mode: 'insensitive' } },
    ]
  }

  return await prisma.product.findMany({
    where,
    orderBy: { createdAt: 'desc' },
  })
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: SearchParams
}) {
  const products = await getProducts(searchParams)

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="mb-8 text-4xl font-bold">All Products</h1>
      
      {products.length === 0 ? (
        <p className="text-gray-500">No products found.</p>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {products.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      )}
    </div>
  )
}